import { ChangeDetectionStrategy, Component, computed, inject, Injectable, signal } from '@angular/core';
import { MatButton, MatIconButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../../app.paths';
import { AuthStore } from '../../../core/auth/auth.store';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { IconName } from '../../../core/icons/icons';
import { readStoredSet, writeStoredSet } from '../../../core/stored';

const STORAGE_KEY = 'mintrack.welcomeHidden';

/** The users who hid the welcome on this device. */
@Injectable({ providedIn: 'root' })
export class WelcomeChoice {
  private readonly user = inject(AuthStore).$user;
  private readonly $hiddenFor = signal(readStoredSet(STORAGE_KEY));

  /** Whether the signed-in user hid the welcome. */
  readonly hidden = computed(() => {
    const user = this.user();
    return !!user && this.$hiddenFor().has(user.id);
  });

  hide(): void {
    const user = this.user();
    if (!user) return;
    const next = new Set(this.$hiddenFor()).add(user.id);
    this.$hiddenFor.set(next);
    writeStoredSet(STORAGE_KEY, next);
  }
}

interface Step {
  icon: IconName;
  title: TranslationPath<'app'>;
  text: TranslationPath<'app'>;
  links: { label: TranslationPath<'app'>; path: string; fragment?: string }[];
}

/**
 * The watch list of someone whose library is empty, as after the first sign-in: three steps to fill it (import a
 * history, find shows, turn on notifications), until hidden.
 */
@Component({
  selector: 'app-welcome',
  imports: [MatButton, MatIconButton, MatIcon, RouterLink],
  template: `
    <header class="flex items-start gap-2">
      <div class="flex min-w-0 flex-1 flex-col gap-1 pt-2">
        <h2 class="[font:var(--mat-sys-headline-small)]">{{ translate('app.welcome.title') }}</h2>
        <p class="text-on-surface-variant [font:var(--mat-sys-body-medium)]">{{ translate('app.welcome.intro') }}</p>
      </div>
      <button
        matIconButton
        type="button"
        class="size-12! shrink-0"
        [attr.aria-label]="translate('app.welcome.dismiss')"
        (click)="choice.hide()">
        <mat-icon svgIcon="close" aria-hidden="true" />
      </button>
    </header>
    <ol class="flex flex-col gap-3">
      @for (step of steps; track step.icon) {
        <li class="step enter" [style.--i]="$index">
          <span class="badge"><mat-icon [svgIcon]="step.icon" aria-hidden="true" /></span>
          <div class="flex min-w-0 flex-col gap-1">
            <h3 class="[font:var(--mat-sys-title-medium)]">{{ translate(step.title) }}</h3>
            <p class="text-on-surface-variant [font:var(--mat-sys-body-medium)]">{{ translate(step.text) }}</p>
            <div class="flex flex-wrap gap-2 pt-2">
              @for (link of step.links; track link.label) {
                <a matButton="tonal" class="min-h-12" [routerLink]="link.path" [fragment]="link.fragment">
                  {{ translate(link.label) }}
                </a>
              }
            </div>
          </div>
        </li>
      }
    </ol>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      gap: 24px;
      max-width: 40rem;
      padding: 16px;
    }
    /* A step: its icon, then what it is for and where to do it, on a card of its own. */
    .step {
      display: flex;
      gap: 16px;
      padding: 16px;
      border-radius: var(--mat-sys-corner-large);
      background: var(--mat-sys-surface-container-low);
    }
    .badge {
      display: grid;
      flex-shrink: 0;
      place-items: center;
      width: 40px;
      height: 40px;
      border-radius: var(--mat-sys-corner-full);
      background: var(--mat-sys-secondary-container);
      color: var(--mat-sys-on-secondary-container);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Welcome {
  protected readonly translate = injectTranslator('app');
  protected readonly choice = inject(WelcomeChoice);

  // Fragments name the Settings sections, which the content scrolls to.
  protected readonly steps: Step[] = [
    {
      icon: 'history',
      title: 'app.welcome.import.title',
      text: 'app.welcome.import.text',
      links: [
        { label: 'app.welcome.import.file', path: appRoutes.settings(), fragment: 'settings-imports' },
        { label: 'app.welcome.import.jellyfin', path: appRoutes.settings(), fragment: 'settings-integrations' },
      ],
    },
    {
      icon: 'explore',
      title: 'app.welcome.discover.title',
      text: 'app.welcome.discover.text',
      links: [{ label: 'app.welcome.discover.action', path: appRoutes.discover() }],
    },
    {
      icon: 'notifications',
      title: 'app.welcome.notifications.title',
      text: 'app.welcome.notifications.text',
      links: [{ label: 'app.welcome.notifications.action', path: appRoutes.pushHelp() }],
    },
  ];
}
