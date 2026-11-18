import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { IconName } from '../core/icons/icons';

/** An empty place: an icon, what the place is for and why it is empty (the content), and one way to fill it. */
@Component({
  selector: 'app-empty-state',
  imports: [MatIcon, MatButton, RouterLink],
  template: `
    <span class="badge"><mat-icon [svgIcon]="icon()" aria-hidden="true" /></span>
    @if (title(); as title) {
      <p class="[font:var(--mat-sys-title-medium)]">{{ title }}</p>
    }
    <p class="text-on-surface-variant [font:var(--mat-sys-body-medium)]"><ng-content /></p>
    @if (actionLink(); as link) {
      <a matButton="tonal" class="mt-2 min-h-12" [routerLink]="link">{{ actionLabel() }}</a>
    }
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      max-width: 40ch;
      margin-inline: auto;
      padding: 48px 16px;
      text-align: center;
      animation: rise-in var(--duration-medium) var(--ease-emph-decel) both;
    }
    .badge {
      display: grid;
      place-items: center;
      width: 64px;
      height: 64px;
      margin-bottom: 8px;
      border-radius: 50%;
      background: var(--mat-sys-secondary-container);
      color: var(--mat-sys-on-secondary-container);
    }
    .badge mat-icon {
      width: 32px;
      height: 32px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EmptyState {
  readonly icon = input.required<IconName>();
  readonly title = input<string | null>(null);
  readonly actionLink = input<string | null>(null);
  readonly actionLabel = input('');
}
