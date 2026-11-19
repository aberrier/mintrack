import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Haptics, TAP_MS, TEST_PATTERN } from './haptics';

describe('Haptics', () => {
  let vibrate: ReturnType<typeof vi.fn>;
  let reducedMotion: boolean;
  let touchScreen: boolean;

  function haptics(withVibration = true, accepted = true): Haptics {
    vibrate = vi.fn(() => accepted);
    const window = {
      navigator: withVibration ? { vibrate } : {},
      matchMedia: (query: string) => ({
        matches: query.includes('coarse') ? touchScreen : query.includes('reduce') && reducedMotion,
      }),
    };
    TestBed.configureTestingModule({ providers: [{ provide: DOCUMENT, useValue: { defaultView: window } }] });
    return TestBed.inject(Haptics);
  }

  beforeEach(() => {
    reducedMotion = false;
    touchScreen = true;
    localStorage.clear();
  });

  it('vibrates long enough to be felt on a tap, even when the user prefers reduced motion', () => {
    reducedMotion = true;

    haptics().tap();

    expect(TAP_MS).toBeGreaterThanOrEqual(20);
    expect(vibrate).toHaveBeenCalledExactlyOnceWith(TAP_MS);
  });

  it('stays still once turned off, and remembers it on this device', () => {
    haptics().setEnabled(false);
    TestBed.resetTestingModule();

    const again = haptics();
    again.tap();

    expect(again.enabled()).toBe(false);
    expect(vibrate).not.toHaveBeenCalled();
  });

  it('vibrates the test pattern even while turned off, and says whether the browser accepted it', () => {
    const service = haptics();
    service.setEnabled(false);

    expect(service.test()).toBe(true);
    expect(vibrate).toHaveBeenCalledExactlyOnceWith(TEST_PATTERN);
    TestBed.resetTestingModule();
    expect(haptics(true, false).test()).toBe(false);
  });

  it('is not offered where the browser cannot vibrate, as on iOS', () => {
    const service = haptics(false);

    expect(service.supported).toBe(false);
    expect(() => service.tap()).not.toThrow();
    expect(service.test()).toBe(false);
  });

  it('is not offered on a desktop, whose browser has the API but nothing to vibrate', () => {
    touchScreen = false;

    const service = haptics();
    service.tap();

    expect(service.supported).toBe(false);
    expect(service.test()).toBe(false);
    expect(vibrate).not.toHaveBeenCalled();
  });
});
