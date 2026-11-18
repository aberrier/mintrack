import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { CheckMark } from './check-mark';

/**
 * A watched check in a 48px target: on a button it marks something in one tap, on a span it only shows it is
 * watched. The element carries the name and, for a toggle, `aria-pressed`.
 */
@Component({
  selector: 'button[appCheckButton], span[appCheckButton]',
  imports: [CheckMark],
  template: '<app-check-mark [done]="done()" />',
  host: { class: 'check' },
  styles: `
    :host {
      display: grid;
      flex: none;
      place-items: center;
      width: 48px;
      height: 48px;
      padding: 0;
      border: 0;
      border-radius: var(--mat-sys-corner-full);
      background: none;
      cursor: pointer;
    }
    :host(span) {
      cursor: default;
    }
    :host(:disabled) {
      opacity: 0.38;
      cursor: default;
    }
    app-check-mark {
      transition: transform var(--duration-short) var(--ease-standard);
    }
    :host(:active:enabled) app-check-mark {
      transform: scale(0.9);
    }
    :host(:focus-visible) {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -2px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CheckButton {
  readonly done = input(false);
}
