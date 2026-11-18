import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { injectTranslator } from '../core/i18n';

/** Why something could not load, next to where it would be, and Try again when trying again can help. */
@Component({
  selector: 'app-load-error',
  imports: [MatIcon],
  template: `
    <p role="alert" class="text-on-surface-variant [font:var(--mat-sys-body-large)]">{{ message() }}</p>
    @if (retryable()) {
      <button type="button" class="text-button flex items-center gap-2" (click)="retry.emit()">
        <mat-icon svgIcon="refresh" aria-hidden="true" />
        {{ translate('app.common.retry') }}
      </button>
    }
  `,
  host: { class: 'flex flex-col items-start gap-2 px-4 py-4' },
  styles: `
    .text-button {
      align-self: flex-start;
      margin-inline-start: -16px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoadError {
  protected readonly translate = injectTranslator('app');

  readonly message = input.required<string>();
  readonly retryable = input(true);
  readonly retry = output<void>();
}
