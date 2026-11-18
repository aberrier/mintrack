import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatIcon } from '@angular/material/icon';

/**
 * A watched mark: an outlined circle with a check, cross-fading to a filled one that pops in once done. Decorative:
 * the button around it carries the name and the pressed state.
 */
@Component({
  selector: 'app-check-mark',
  imports: [MatIcon],
  template: `
    <mat-icon svgIcon="check_circle" class="outlined" aria-hidden="true" />
    <mat-icon svgIcon="check_circle_fill" class="filled" aria-hidden="true" />
  `,
  host: { '[class.done]': 'done()' },
  styles: `
    :host {
      display: grid;
      flex: none;
      width: 36px;
      height: 36px;
      border-radius: 50%;
    }
    mat-icon {
      grid-area: 1 / 1;
      width: 100%;
      height: 100%;
      transition:
        opacity var(--duration-toggle) var(--ease-standard),
        transform var(--duration-medium) var(--ease-pop);
    }
    .outlined {
      color: var(--mat-sys-on-surface-variant);
    }
    .filled {
      color: var(--mat-sys-primary);
      opacity: 0;
      transform: scale(0.5);
    }
    :host(.done) .outlined {
      opacity: 0;
      transform: scale(0.8);
    }
    :host(.done) .filled {
      opacity: 1;
      transform: none;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CheckMark {
  readonly done = input(false);
}
