import { afterNextRender, ChangeDetectionStrategy, Component, ElementRef, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../app.paths';
import { injectTranslator } from '../../core/i18n';
import { ViewToggle } from '../../shared/view-toggle';

/** The Episodes tab's header, kept on top while the page scrolls: Watch list | Upcoming, and the view toggle. */
@Component({
  selector: 'app-episodes-tabs',
  imports: [RouterLink, ViewToggle],
  template: `
    <header class="header tabs items-center">
      <nav class="flex min-w-0 flex-1 self-stretch" [attr.aria-label]="translate('app.nav.episodes')">
        <a
          class="tab"
          [routerLink]="routes.watchList()"
          replaceUrl
          [class.active]="active() === 'watchList'"
          [attr.aria-current]="active() === 'watchList' ? 'page' : null"
          (click)="keepFocus()"
          >{{ translate('app.episodes.watchList') }}</a
        >
        <a
          class="tab"
          [routerLink]="routes.upcoming()"
          replaceUrl
          (click)="keepFocus()"
          [class.active]="active() === 'upcoming'"
          [attr.aria-current]="active() === 'upcoming' ? 'page' : null"
          >{{ translate('app.episodes.upcoming') }}</a
        >
      </nav>
      <app-view-toggle [key]="active()" />
    </header>
  `,
  styles: `
    :host {
      position: sticky;
      top: 0;
      z-index: 2;
      display: block;
    }
    .header {
      padding-inline-end: 4px;
      background: var(--mat-sys-surface);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EpisodesTabs {
  protected readonly translate = injectTranslator('app');
  protected readonly routes = appRoutes;

  /** The open sub-tab, also the key under which its list or grid choice is remembered. */
  readonly active = input.required<'watchList' | 'upcoming'>();

  constructor() {
    const host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    // Each sub-tab is its own page: the focus moves to the tab now open rather than falling back to the page.
    afterNextRender(() => {
      if (!focusOnArrival) return;
      focusOnArrival = false;
      host.querySelector<HTMLElement>('[aria-current="page"]')?.focus();
    });
  }

  protected keepFocus(): void {
    focusOnArrival = true;
  }
}

/** A sub-tab was chosen: the next page's header takes the focus. */
let focusOnArrival = false;
