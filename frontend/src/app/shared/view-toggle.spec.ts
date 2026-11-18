import { TestBed } from '@angular/core/testing';
import { ViewModes, ViewToggle } from './view-toggle';

describe('ViewToggle', () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('switches between list and grid, and the choice is remembered on the device', async () => {
    const fixture = TestBed.createComponent(ViewToggle);
    fixture.componentRef.setInput('key', 'watchList');
    await fixture.whenStable();
    const button = (fixture.nativeElement as HTMLElement).querySelector('button')!;
    expect(button.getAttribute('aria-label')).toBe('Show as grid');

    button.click();
    await fixture.whenStable();

    expect(button.getAttribute('aria-label')).toBe('Show as list');
    expect(TestBed.inject(ViewModes).mode('watchList')()).toBe('grid');
    expect(localStorage.getItem('mintrack.view.watchList')).toBe('grid');
    expect(TestBed.inject(ViewModes).mode('upcoming')()).toBe('list');
  });

  it('reads the remembered choice, and still switches when storage is unavailable', () => {
    localStorage.setItem('mintrack.view.upcoming', 'grid');
    expect(TestBed.inject(ViewModes).mode('upcoming')()).toBe('grid');

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const modes = TestBed.inject(ViewModes);

    expect(modes.mode('watchList')()).toBe('list');
    modes.set('watchList', 'grid');
    expect(modes.mode('watchList')()).toBe('grid');
  });
});
