import { DOCUMENT, inject, Injectable, signal } from '@angular/core';
import { readStored, writeStored } from './stored';

const STORAGE_KEY = 'mintrack.haptics';
/** Long enough to be felt on most Android phones, short enough to read as a tick. */
const TAP_MS = 15;

/**
 * A short vibration confirming a tap that changed the library: a check, a season, an added title. Only on a touch
 * screen whose browser has the Vibration API (Android, not iOS; desktop browsers have the API but nothing to vibrate),
 * never when the user prefers reduced motion, and only while the switch in Settings is on, remembered on this device.
 */
@Injectable({ providedIn: 'root' })
export class Haptics {
  private readonly window = inject(DOCUMENT).defaultView;
  private readonly $enabled = signal(readStored(STORAGE_KEY) !== 'off');

  /** The device can vibrate, so the Settings switch has an effect. */
  readonly supported =
    typeof this.window?.navigator.vibrate === 'function' && !!this.window.matchMedia?.('(pointer: coarse)').matches;
  readonly enabled = this.$enabled.asReadonly();

  setEnabled(enabled: boolean): void {
    this.$enabled.set(enabled);
    writeStored(STORAGE_KEY, enabled ? 'on' : 'off');
  }

  /** Vibrate once, briefly, when allowed. Must run while handling the tap: browsers ignore it otherwise. */
  tap(): void {
    if (!this.supported || !this.$enabled()) return;
    if (this.window?.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    this.window?.navigator.vibrate(TAP_MS);
  }
}
