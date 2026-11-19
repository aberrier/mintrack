import { DOCUMENT, inject, Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'mintrack.haptics';
/** Long enough to be felt on most Android phones, short enough to read as a tick. */
const TAP_MS = 15;

/**
 * A short vibration confirming a tap that changed the library: a check, a season, an added title. Only where the
 * browser has the Vibration API (Android, not iOS), never when the user prefers reduced motion, and only while the
 * switch in Settings is on, remembered on this device. Storage may be unavailable: the choice then lasts until the app
 * reloads.
 */
@Injectable({ providedIn: 'root' })
export class Haptics {
  private readonly window = inject(DOCUMENT).defaultView;
  private readonly $enabled = signal(readEnabled());

  /** The browser can vibrate, so the Settings switch has an effect. */
  readonly supported = typeof this.window?.navigator.vibrate === 'function';
  readonly enabled = this.$enabled.asReadonly();

  setEnabled(enabled: boolean): void {
    this.$enabled.set(enabled);
    try {
      localStorage.setItem(STORAGE_KEY, enabled ? 'on' : 'off');
    } catch {
      // Kept in memory only.
    }
  }

  /** Vibrate once, briefly, when allowed. Must run while handling the tap: browsers ignore it otherwise. */
  tap(): void {
    if (!this.supported || !this.$enabled()) return;
    if (this.window?.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    this.window?.navigator.vibrate(TAP_MS);
  }
}

function readEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== 'off';
  } catch {
    return true;
  }
}
