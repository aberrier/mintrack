import { Location } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { MatIconButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { Router } from '@angular/router';
import { injectTranslator } from '../core/i18n';

/**
 * Back, for pages outside the bottom navigation: an installed app has no browser back button. It goes back in the
 * app's history, or to `fallback` (the page's tab) when the page was opened first, as from a link or a reload.
 */
@Component({
  selector: 'app-back-button',
  imports: [MatIconButton, MatIcon],
  template: `
    <button
      matIconButton
      type="button"
      class="size-12!"
      [attr.aria-label]="translate('app.common.back')"
      (click)="back()"
      data-testid="back">
      <mat-icon svgIcon="arrow_back" aria-hidden="true" />
    </button>
  `,
  styles: `
    :host {
      display: block;
      width: fit-content;
      border-radius: var(--mat-sys-corner-full);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BackButton {
  protected readonly translate = injectTranslator('app');
  private readonly router = inject(Router);
  private readonly location = inject(Location);

  /** Where back goes when the app has no earlier page. */
  readonly fallback = input.required<string>();

  protected back(): void {
    if (this.router.lastSuccessfulNavigation()?.previousNavigation) this.location.back();
    else void this.router.navigateByUrl(this.fallback());
  }
}
