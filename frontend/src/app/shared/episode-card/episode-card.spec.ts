import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CardEpisode, EpisodeCard } from './episode-card';

const EPISODE: CardEpisode = {
  tmdb_id: 7,
  show_title: 'Andor',
  poster_path: null,
  season_number: 1,
  episode_number: 5,
  title: 'The Axe Forgets',
  remaining: 3,
};

describe('EpisodeCard', () => {
  let fixture: ComponentFixture<EpisodeCard>;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    fixture = TestBed.createComponent(EpisodeCard);
    fixture.componentRef.setInput('episode', EPISODE);
  });

  async function render(inputs: Record<string, unknown> = {}): Promise<HTMLElement> {
    for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  const text = (element: Element | null) => element?.textContent?.replace(/\s+/g, ' ').trim();

  it('shows the show, the episode number with how many follow, and the title, linking to the show', async () => {
    const card = await render();

    expect(text(card.querySelector('h3'))).toBe('Andor');
    expect(text(card.querySelector('[data-testid="episode-code"]'))).toBe('S01 | E05+3');
    expect(text(card.querySelector('[data-testid="episode-title"]'))).toBe('The Axe Forgets');
    expect(card.querySelector('a')?.getAttribute('href')).toBe('/shows/7');
  });

  it('marks the episode in one tap on a check named after it', async () => {
    const checked = vi.fn();
    fixture.componentInstance.check.subscribe(checked);
    const card = await render({ checkable: true });

    const check = card.querySelector<HTMLButtonElement>('button.check')!;
    expect(check.getAttribute('aria-label')).toBe('Mark S01 | E05 of Andor watched');
    check.click();

    expect(checked).toHaveBeenCalledOnce();
  });

  it('offers its actions from a named menu, and hides the swiped-to buttons while closed', async () => {
    const card = await render({ actions: [{ id: 'stopped', label: 'Stop watching', icon: 'block' }] });

    expect(card.querySelector('button[aria-label="More for Andor"]')).not.toBeNull();
    const swiped = card.querySelector('.actions')!;
    expect(swiped.getAttribute('aria-hidden')).toBe('true');
    expect(swiped.hasAttribute('inert')).toBe(true);
  });

  it('in a grid, names the poster link after the whole episode', async () => {
    const card = await render({ variant: 'grid', checkable: true });

    expect(card.querySelector('a')?.getAttribute('aria-label')).toBe('Andor, S01 | E05, The Axe Forgets');
    expect(card.querySelector('button.check')).not.toBeNull();
  });

  it('shows a movie of the history by its title, watched', async () => {
    const card = await render({
      episode: { ...EPISODE, media_type: 'movie', season_number: null, episode_number: null, title: null },
      watched: true,
    });

    expect(card.querySelector('[data-testid="episode-code"]')).toBeNull();
    expect(card.querySelector('a')?.getAttribute('href')).toBe('/movies/7');
    expect(card.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('Watched');
  });
});
