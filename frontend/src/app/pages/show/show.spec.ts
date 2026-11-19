import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideRouter } from '@angular/router';
import { of, Subject } from 'rxjs';
import { CHECKED_PAUSE_MS } from '../../core/tracking/watch-list.store';
import { Confetti } from '../../shared/confetti';
import Show from './show';

function episode(season: number, number: number, airDate: string | null): Model.Http.Episode {
  return {
    id: `${season}x${number}`,
    season_number: season,
    episode_number: number,
    title: '',
    air_date: airDate,
    airstamp: null,
  };
}

const EPISODES: Record<number, Model.Http.Episode[]> = {
  1: [episode(1, 1, '2020-01-01'), episode(1, 2, '2020-01-08')],
  2: [episode(2, 1, '2020-02-01'), episode(2, 2, '2999-01-01'), episode(2, 3, null)],
  0: [episode(0, 1, '2020-01-02')],
};
/** Season 2 has one episode to come and one without a date. */
const AIRED: Record<number, number> = { 1: 2, 2: 1, 0: 1 };

function show(
  watched: string[],
  tmdbStatus = 'Ended',
  nextEpisode: Model.Http.NextEpisode | null = null,
): Model.Http.Show {
  return {
    tmdb_id: 7,
    title: 'Show',
    overview: '',
    poster_path: null,
    release_date: '2020-01-01',
    tmdb_status: tmdbStatus,
    backdrop_path: null,
    network: 'Channel',
    runtime: null,
    seasons: [1, 2, 0].map((number) => ({
      season_number: number,
      title: number ? `Season ${number}` : 'Specials',
      episode_count: EPISODES[number].length,
      watched_count: watched.filter((id) => id.startsWith(`${number}x`)).length,
      aired_count: AIRED[number],
    })),
    tracking: { status: 'watching', watched: Object.fromEntries(watched.map((id) => [id, '2020-03-01T00:00:00Z'])) },
    next_episode: nextEpisode,
  };
}

describe('Show', () => {
  let fixture: ComponentFixture<Show>;
  let http: HttpTestingController;
  let confetti: { launch: ReturnType<typeof vi.fn> };
  let dialog: { open: ReturnType<typeof vi.fn> };
  let snackBar: { open: ReturnType<typeof vi.fn> };

  async function open(loaded: Model.Http.Show): Promise<HTMLElement> {
    confetti = { launch: vi.fn() };
    dialog = { open: vi.fn(() => ({ afterClosed: () => of(true) })) };
    snackBar = { open: vi.fn(() => ({ onAction: () => of(), afterDismissed: () => new Subject() })) };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Confetti, useValue: confetti },
        { provide: MatDialog, useValue: dialog },
        { provide: MatSnackBar, useValue: snackBar },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Show);
    fixture.componentRef.setInput('tmdbId', 7);
    // The resource sends its request from an effect.
    TestBed.tick();
    http.expectOne('/api/shows/7').flush(loaded);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function button(page: HTMLElement, name: string): HTMLButtonElement | undefined {
    return [...page.querySelectorAll('button')].find(
      (b) => (b.getAttribute('aria-label') ?? b.textContent)?.trim() === name,
    );
  }

  function watched(ids: string[], status: Model.Http.TrackingStatus, check = true): void {
    const request = http.expectOne('/api/shows/7/watched');
    if (check) expect(request.request.body).toEqual({ episode_ids: ids, watched: true });
    request.flush({ status, watched: Object.fromEntries(ids.map((id) => [id, '2026-01-01T00:00:00Z'])) });
  }

  function sentIds(watched: boolean): string[] {
    const request = http.expectOne('/api/shows/7/watched');
    expect(request.request.body.watched).toBe(watched);
    return request.request.body.episode_ids as string[];
  }

  const code = (page: HTMLElement) =>
    page.querySelector('[data-testid="watch-next"] [data-testid="episode-code"]')?.textContent?.replace(/\s+/g, '');

  /** Answer the request for a season's episodes. */
  function season(number: number): void {
    http.expectOne(`/api/shows/7/seasons/${number}`).flush({ season_number: number, episodes: EPISODES[number] });
  }

  async function expand(page: HTMLElement, index: number, number: number): Promise<void> {
    [...page.querySelectorAll<HTMLButtonElement>('button[aria-expanded]')][index].click();
    season(number);
    await fixture.whenStable();
  }

  it('marks a season in one tap from its counts, then sends its aired, dated episodes once loaded', async () => {
    const page = await open(show([], 'Returning Series'));

    button(page, 'Mark Season 2 watched')!.click();
    await fixture.whenStable();

    expect(page.textContent).toContain('1/1');
    season(2);
    expect(sentIds(true)).toEqual(['2x1']);
  });

  it('asks before unmarking a fully watched season, then unmarks it', async () => {
    const page = await open(show(['1x1', '1x2'], 'Returning Series'));
    const check = button(page, 'Mark Season 1 watched')!;
    expect(check.getAttribute('aria-pressed')).toBe('true');

    check.click();

    expect(dialog.open).toHaveBeenCalledOnce();
    season(1);
    expect(sentIds(false)).toEqual(['1x1', '1x2']);
  });

  it('loads and renders a season’s episodes only once it is open', async () => {
    const page = await open(show([]));
    expect(button(page, 'Season 1, episode 1')).toBeUndefined();

    await expand(page, 0, 1);

    expect(button(page, 'Season 1, episode 1')).toBeDefined();
  });

  it('says when a season cannot load, and loads it on Try again', async () => {
    const page = await open(show([]));
    [...page.querySelectorAll<HTMLButtonElement>('button[aria-expanded]')][0].click();
    http.expectOne('/api/shows/7/seasons/1').flush('down', { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(page.textContent).toContain('Cannot load this season’s episodes.');
    button(page, 'Try again')!.click();
    season(1);
    await fixture.whenStable();

    expect(button(page, 'Season 1, episode 1')).toBeDefined();
  });

  it('offers the episode the server says is next, checks it at once, then shows the server’s next one', async () => {
    const page = await open(show(['1x1'], 'Returning Series', { ...EPISODES[1][1], remaining: 1 }));
    expect(code(page)).toBe('S01|E02+1');

    button(page, 'Mark season 1 episode 2 of Show watched')!.click();
    await fixture.whenStable();

    // The seasons are not loaded: the card stays, checked, until the server says what comes next.
    expect(code(page)).toBe('S01|E02+1');
    watched(['1x2'], 'up_to_date');
    await fixture.whenStable();
    http.expectOne('/api/shows/7').flush(show(['1x1', '1x2'], 'Returning Series', { ...EPISODES[2][0], remaining: 0 }));
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, CHECKED_PAUSE_MS + 10));
    await fixture.whenStable();

    expect(code(page)).toBe('S02|E01');
  });

  it('offers to undo a Watch next check, unmarking the episode', async () => {
    const undo = new Subject<void>();
    const page = await open(show(['1x1'], 'Returning Series', { ...EPISODES[1][1], remaining: 1 }));
    snackBar.open.mockReturnValue({ onAction: () => undo, afterDismissed: () => new Subject() });

    button(page, 'Mark season 1 episode 2 of Show watched')!.click();
    expect(snackBar.open).toHaveBeenCalledWith('S01E02 watched', 'Undo', { duration: 10_000 });
    watched(['1x2'], 'watching');
    undo.next();

    expect(sentIds(false)).toEqual(['1x2']);
  });

  it('keeps the Watch next card’s place from adding the show until the server says which episode', async () => {
    const page = await open({ ...show([]), tracking: null });
    const pending = () => !!page.querySelector('[data-testid="watch-next-pending"]');
    expect(pending()).toBe(false);

    button(page, 'Add to library')!.click();
    await fixture.whenStable();
    expect(pending()).toBe(true);
    http.expectOne('/api/shows/7/tracking').flush({ status: 'not_started', watched: {} });
    await fixture.whenStable();
    expect(pending()).toBe(true);
    http.expectOne('/api/shows/7').flush({
      ...show([], 'Ended', { ...EPISODES[1][0], remaining: 1 }),
      tracking: { status: 'not_started', watched: {} },
    });
    await fixture.whenStable();

    expect(pending()).toBe(false);
    expect(code(page)).toBe('S01|E01+1');
  });

  it('offers the earlier unwatched episodes, counting seasons not loaded, and marks them on request', async () => {
    const accept = new Subject<void>();
    const page = await open(show([], 'Returning Series'));
    snackBar.open.mockReturnValue({ onAction: () => accept, afterDismissed: () => new Subject() });
    await expand(page, 1, 2);

    button(page, 'Season 2, episode 1')!.click();

    expect(snackBar.open).toHaveBeenCalledWith('2 earlier episodes are not watched.', 'Mark watched', {
      duration: 10_000,
    });
    watched(['2x1'], 'watching');
    accept.next();
    season(1);
    watched(['1x1', '1x2'], 'watching', false);
  });

  it('throws confetti once the server says the show is finished', async () => {
    const page = await open(show(['1x1', '1x2']));

    button(page, 'Mark Season 2 watched')!.click();
    season(2);
    expect(confetti.launch).not.toHaveBeenCalled();
    watched(['2x1'], 'finished');

    expect(confetti.launch).toHaveBeenCalledOnce();
  });

  it('throws no confetti while the server says the show goes on', async () => {
    const page = await open(show(['1x1', '1x2'], 'Returning Series'));

    button(page, 'Mark Season 2 watched')!.click();
    season(2);
    watched(['2x1'], 'up_to_date');

    expect(confetti.launch).not.toHaveBeenCalled();
  });

  it('shows the first air date as a date, not as the server sends it', async () => {
    const page = await open(show([]));
    fixture.componentRef.setInput('tab', 'about');
    await fixture.whenStable();

    expect(page.querySelector('dl')?.textContent).toContain('1 Jan 2020');
    expect(page.querySelector('dl')?.textContent).not.toContain('2020-01-01');
  });
});
