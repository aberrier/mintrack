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
  // Entering pops in with a slight overshoot; leaving is shorter and plain, so unchecking never replays the pop.
  styles: `
    :host {
      display: grid;
      flex: none;
      width: 36px;
      height: 36px;
      border-radius: var(--mat-sys-corner-full);
      background: var(--check-backdrop, none);
    }
    mat-icon {
      grid-area: 1 / 1;
      width: 100%;
      height: 100%;
      transition:
        opacity var(--duration-exit) var(--ease-emph-accel),
        transform var(--duration-exit) var(--ease-emph-accel);
    }
    .outlined {
      color: var(--mat-sys-on-surface-variant);
      transition:
        opacity var(--duration-toggle) var(--ease-standard),
        transform var(--duration-toggle) var(--ease-standard);
    }
    .filled {
      color: var(--mat-sys-primary);
      opacity: 0;
      transform: scale(0.5);
    }
    :host(.done) .outlined {
      opacity: 0;
      transform: scale(0.8);
      transition:
        opacity var(--duration-exit) var(--ease-emph-accel),
        transform var(--duration-exit) var(--ease-emph-accel);
    }
    :host(.done) .filled {
      opacity: 1;
      transform: none;
      transition:
        opacity var(--duration-toggle) var(--ease-standard),
        transform var(--duration-medium) var(--ease-pop);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CheckMark {
  readonly done = input(false);
}
