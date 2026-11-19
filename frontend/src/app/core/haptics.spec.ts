import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Haptics } from './haptics';

describe('Haptics', () => {
  let vibrate: ReturnType<typeof vi.fn>;
  let reducedMotion: boolean;

  function haptics(withVibration = true): Haptics {
    vibrate = vi.fn(() => true);
    const window = {
      navigator: withVibration ? { vibrate } : {},
      matchMedia: (query: string) => ({ matches: query.includes('reduce') && reducedMotion }),
    };
    TestBed.configureTestingModule({ providers: [{ provide: DOCUMENT, useValue: { defaultView: window } }] });
    return TestBed.inject(Haptics);
  }

  beforeEach(() => {
    reducedMotion = false;
    localStorage.clear();
  });

  it('vibrates briefly on a tap', () => {
    haptics().tap();

    expect(vibrate).toHaveBeenCalledExactlyOnceWith(15);
  });

  it('stays still when the user prefers reduced motion', () => {
    reducedMotion = true;

    haptics().tap();

    expect(vibrate).not.toHaveBeenCalled();
  });

  it('stays still once turned off, and remembers it on this device', () => {
    haptics().setEnabled(false);
    TestBed.resetTestingModule();

    const again = haptics();
    again.tap();

    expect(again.enabled()).toBe(false);
    expect(vibrate).not.toHaveBeenCalled();
  });

  it('is not offered where the browser cannot vibrate, as on iOS', () => {
    const service = haptics(false);

    expect(service.supported).toBe(false);
    expect(() => service.tap()).not.toThrow();
  });
});
