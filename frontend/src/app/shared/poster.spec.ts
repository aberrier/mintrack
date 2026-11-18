import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Poster } from './poster';

describe('Poster', () => {
  let fixture: ComponentFixture<Poster>;

  beforeEach(() => {
    fixture = TestBed.createComponent(Poster);
    fixture.componentRef.setInput('path', '/poster.jpg');
    fixture.componentRef.setInput('label', 'Andor');
  });

  async function render(inputs: Record<string, unknown> = {}): Promise<HTMLElement> {
    for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the TMDB image, with neither badge nor button by default', async () => {
    const poster = await render();

    expect(poster.querySelector('img')?.getAttribute('src')).toBe('https://image.tmdb.org/t/p/w185/poster.jpg');
    expect(poster.querySelector('[data-testid="finished-badge"]')).toBeNull();
    expect(poster.querySelector('button')).toBeNull();
  });

  it('carries a Finished badge on finished shows', async () => {
    const poster = await render({ finished: true });

    expect(poster.querySelector('[data-testid="finished-badge"]')?.textContent?.trim()).toBe('Finished');
  });

  it('offers to add the title, then says it is in the library', async () => {
    const added = vi.fn();
    fixture.componentInstance.add.subscribe(added);
    let poster = await render({ tracked: false });

    poster.querySelector('button')!.click();
    expect(added).toHaveBeenCalledOnce();
    expect(poster.querySelector('button')?.getAttribute('aria-label')).toBe('Add Andor');

    poster = await render({ tracked: true });
    const check = poster.querySelector('button')!;
    expect(check.getAttribute('aria-label')).toBe('Andor, in your library');
    expect(check.getAttribute('aria-disabled')).toBe('true');
    check.click();
    expect(added).toHaveBeenCalledOnce();
  });
});
