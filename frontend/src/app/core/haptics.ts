import { DOCUMENT, inject, Injectable, signal } from '@angular/core';
import { readStored, writeStored } from './stored';

const STORAGE_KEY = 'mintrack.haptics';
/** Long enough for the slow vibration motors of many Android phones to be felt, short enough to read as a tick. */
const TAP_MS = 30;

/**
 * A short vibration confirming a tap that changed the library: a check, a season, an added title. Only on a touch
 * screen whose browser has the Vibration API (Android, not iOS; desktop browsers have the API but nothing to vibrate),
 * and only while the switch in Settings is on, remembered on this device. Reduced motion does not silence it: a
 * vibration moves nothing on screen.
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

  /** Vibrate once, briefly, when allowed. Must run while handling the tap: browsers may ignore it otherwise. */
  tap(): void {
    if (this.supported && this.$enabled()) this.window?.navigator.vibrate(TAP_MS);
  }
}
