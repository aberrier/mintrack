import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Subject } from 'rxjs';
import { Confetti } from '../../shared/confetti';
import { TrackingStore } from './tracking.store';
import { CHECKED_PAUSE_MS, WatchListStore } from './watch-list.store';

const NOW = new Date('2026-06-10T12:00:00Z');

function episode(id: string, season: number, number: number, airDate: string | null): Model.Http.Episode {
  return {
    id,
    season_number: season,
    episode_number: number,
    title: `Episode ${id}`,
    air_date: airDate,
    airstamp: null,
  };
}

const SHOW: Model.Http.Show = {
  tmdb_id: 7,
  title: 'Andor',
  overview: '',
  poster_path: '/andor.jpg',
  release_date: null,
  tmdb_status: 'Returning Series',
  backdrop_path: null,
  network: null,
  runtime: null,
  seasons: [
    { season_number: 1, title: '', episode_count: 3, watched_count: 1, aired_count: 3 },
    { season_number: 2, title: '', episode_count: 1, watched_count: 0, aired_count: 0 },
  ],
  tracking: { status: 'watching', watched: { a: '2026-06-01T00:00:00Z' } },
  next_episode: { ...episode('b', 1, 2, '2026-01-08'), remaining: 1 },
};

const EPISODES: Record<number, Model.Http.Episode[]> = {
  1: [episode('a', 1, 1, '2026-01-01'), episode('b', 1, 2, '2026-01-08'), episode('c', 1, 3, '2026-01-15')],
  2: [episode('d', 2, 1, '2099-01-01')],
};

function card(overrides: Partial<Model.Http.WatchListEpisode> = {}): Model.Http.WatchListEpisode {
  return {
    episode_id: 'b',
    tmdb_id: 7,
    show_title: 'Andor',
    poster_path: '/andor.jpg',
    season_number: 1,
    episode_number: 2,
    title: 'Episode b',
    airstamp: null,
    day: '2026-01-08',
    remaining: 1,
    last_watched_at: '2026-06-01T00:00:00Z',
    section: 'next',
    ...overrides,
  };
}

function entry(id: string, watchedAt: string): Model.Http.HistoryEntry {
  return {
    id,
    media_type: 'tv',
    tmdb_id: 7,
    title: 'Andor',
    poster_path: null,
    season_number: 1,
    episode_number: 1,
    episode_title: 'Pilot',
    watched_at: watchedAt,
    finished: false,
  };
}

describe('WatchListStore', () => {
  let store: WatchListStore;
  let http: HttpTestingController;
  let snackBar: { open: ReturnType<typeof vi.fn> };
  let snackAction: Subject<void>;
  let confetti: { launch: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    snackAction = new Subject();
    snackBar = { open: vi.fn(() => ({ onAction: () => snackAction, afterDismissed: () => new Subject() })) };
    confetti = { launch: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MatSnackBar, useValue: snackBar },
        { provide: Confetti, useValue: confetti },
      ],
    });
    store = TestBed.inject(WatchListStore);
    http = TestBed.inject(HttpTestingController);
  });

  function loadList(episodes: Model.Http.WatchListEpisode[]): void {
    store.load().subscribe();
    http.expectOne('/api/watch-list').flush({ episodes });
  }

  /** The show and its seasons loaded, as after a visit to its page. */
  function loadShow(): void {
    const tracking = TestBed.inject(TrackingStore);
    tracking.loadShow(7).subscribe();
    http.expectOne('/api/shows/7').flush(SHOW);
    for (const number of [1, 2]) {
      tracking.loadSeason(7, number).subscribe();
      http.expectOne(`/api/shows/7/seasons/${number}`).flush({ season_number: number, episodes: EPISODES[number] });
    }
  }

  const settle = () => new Promise((resolve) => setTimeout(resolve));
  /** The moment a checked card stays checked. */
  const pause = () => new Promise((resolve) => setTimeout(resolve, CHECKED_PAUSE_MS + 10));

  it('shows a checked card checked for a moment, then the next episode of the loaded show, before the server answers', async () => {
    loadShow();
    loadList([card()]);

    store.check(store.episodes()![0], NOW);
    store.check(store.episodes()![0], NOW);

    expect(store.episodes()![0].episode_id).toBe('b');
    expect(store.checking().has(7)).toBe(true);
    await pause();
    const [next] = store.episodes()!;
    expect([next.episode_id, next.season_number, next.episode_number, next.remaining]).toEqual(['c', 1, 3, 0]);
    expect(store.checking().size).toBe(0);
    // The second tap, during the moment, marked nothing more.
    const write = http.expectOne('/api/shows/7/watched');
    expect(write.request.body).toEqual({ episode_ids: ['b'], watched: true });
  });

  it('moves a card to the following episode the list carries', async () => {
    loadList([card({ remaining: 2, following: episode('c', 1, 3, '2026-01-15') })]);

    store.check(store.episodes()![0], NOW);
    await pause();

    const [next] = store.episodes()!;
    expect([next.episode_id, next.episode_number, next.remaining]).toEqual(['c', 3, 1]);
    expect(store.checking().size).toBe(0);
  });

  it('takes the card out when the episode the list says follows has not aired', async () => {
    loadList([card({ remaining: 0, following: episode('d', 2, 1, '2099-01-01') })]);

    store.check(store.episodes()![0], NOW);
    await pause();

    expect(store.episodes()).toEqual([]);
  });

  it('keeps a card checked until the server says what follows, ignoring a second tap meanwhile', async () => {
    loadList([card()]);

    store.check(store.episodes()![0], NOW);
    store.check(store.episodes()![0], NOW);

    expect(store.episodes()![0].episode_id).toBe('b');
    expect(store.checking().has(7)).toBe(true);
    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x', b: 'y' } });
    await settle();
    http
      .expectOne('/api/watch-list')
      .flush({ episodes: [card({ episode_id: 'd', season_number: 2, episode_number: 1 })] });

    expect(store.episodes()!.map((e) => e.episode_id)).toEqual(['d']);
    expect(store.checking().size).toBe(0);
  });

  it('puts the previous card back when the check fails, even when the list cannot load again', async () => {
    loadShow();
    loadList([card({ tmdb_id: 1, episode_id: 'x' }), card()]);

    store.check(store.episodes()![1], NOW);
    await pause();
    expect(store.episodes()![1].episode_id).toBe('c');
    http.expectOne('/api/shows/7/watched').error(new ProgressEvent('error'));
    await settle();
    http.expectOne('/api/watch-list').error(new ProgressEvent('error'));

    expect(store.episodes()!.map((e) => e.episode_id)).toEqual(['x', 'b']);
  });

  it('takes the card out when the show is up to date, without loading the show', async () => {
    loadList([card({ episode_id: 'c', episode_number: 3, remaining: 0 })]);

    store.check(store.episodes()![0], NOW);
    await pause();

    expect(store.episodes()).toEqual([]);
    http.expectNone('/api/shows/7');
  });

  it('moves a show not watched for a while to the top of Watch next', async () => {
    loadShow();
    loadList([card({ tmdb_id: 1, episode_id: 'x', section: 'next' }), card({ section: 'dormant' })]);

    store.check(store.episodes()![1], NOW);
    await pause();

    expect(store.episodes()!.map((e) => [e.tmdb_id, e.section])).toEqual([
      [7, 'next'],
      [1, 'next'],
    ]);
  });

  it('throws confetti when the server says the checked episode finished the show', async () => {
    loadList([card({ episode_id: 'c', episode_number: 3, remaining: 0 })]);

    store.check(store.episodes()![0], NOW);
    http.expectOne('/api/shows/7/watched').flush({ status: 'finished', watched: { c: 'x' } });

    expect(confetti.launch).toHaveBeenCalledOnce();
  });

  it('loads the list again and says so when the server refuses the check', async () => {
    loadShow();
    loadList([card()]);

    store.check(store.episodes()![0], NOW);
    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });
    await settle();
    http.expectOne('/api/watch-list').flush({ episodes: [card()] });

    expect(store.episodes()![0].episode_id).toBe('b');
    expect(snackBar.open).toHaveBeenCalledWith('Your change could not be saved.', undefined, { duration: 4000 });
  });

  it('removes a card put aside or stopped at once, offering to undo it', () => {
    loadList([card(), card({ tmdb_id: 8 })]);

    store.remove(store.episodes()![0], 'watch_later');
    store.remove(store.episodes()![0], 'stopped');

    expect(store.episodes()).toEqual([]);
    expect(http.expectOne('/api/shows/7/tracking').request.body).toEqual({ status: 'watch_later' });
    expect(http.expectOne('/api/shows/8/tracking').request.body).toEqual({ status: 'stopped' });
    expect(snackBar.open).toHaveBeenCalledWith('Moved to Watch later', 'Undo', { duration: 10_000 });
    expect(snackBar.open).toHaveBeenCalledWith('Stopped watching', 'Undo', { duration: 10_000 });
  });

  it('puts the card back and resumes the show on Undo', async () => {
    loadList([card({ tmdb_id: 1 }), card(), card({ tmdb_id: 8 })]);

    store.remove(store.episodes()![1], 'watch_later');
    http.expectOne('/api/shows/7/tracking').flush({ status: 'watch_later', watched: {} });
    snackAction.next();

    expect(store.episodes()!.map((e) => e.tmdb_id)).toEqual([1, 7, 8]);
    const resume = http.expectOne('/api/shows/7/tracking');
    expect(resume.request.body).toEqual({ status: 'watching' });
    resume.flush({ status: 'watching', watched: {} });
    await settle();
    http.expectOne('/api/watch-list').flush({ episodes: [card()] });
  });

  it('says when taking a card out fails, and loads the list again', async () => {
    loadList([card()]);

    store.remove(store.episodes()![0], 'stopped');
    http.expectOne('/api/shows/7/tracking').flush('down', { status: 500, statusText: 'Server Error' });
    await settle();
    http.expectOne('/api/watch-list').flush({ episodes: [card()] });

    expect(store.episodes()).toHaveLength(1);
    expect(snackBar.open).toHaveBeenCalledWith('Your change could not be saved.', undefined, { duration: 4000 });
  });

  it('pages through the history from the oldest entry received, until there is no more', () => {
    store.loadOlderHistory();
    http.expectOne('/api/history').flush({ entries: [entry('b', '2026-06-02T00:00:00Z')], has_more: true });

    store.loadOlderHistory();
    const older = http.expectOne((request) => request.url === '/api/history');
    expect(older.request.params.get('before')).toBe('2026-06-02T00:00:00Z');
    expect(older.request.params.get('before_id')).toBe('b');
    older.flush({ entries: [entry('a', '2026-06-01T00:00:00Z')], has_more: false });

    expect(store.history().map((e) => e.id)).toEqual(['b', 'a']);
    expect(store.historyState()).toBe('done');
    store.loadOlderHistory();
    http.expectNone('/api/history');
  });

  it('adds a checked episode to an open history, without showing it twice', () => {
    loadShow();
    loadList([card()]);
    store.loadOlderHistory();
    http.expectOne('/api/history').flush({ entries: [entry('a', '2026-06-01T00:00:00Z')], has_more: true });

    store.check(store.episodes()![0], NOW);
    store.loadOlderHistory();
    http
      .expectOne((request) => request.url === '/api/history')
      .flush({ entries: [entry('b', NOW.toISOString())], has_more: false });

    expect(store.history().map((e) => e.id)).toEqual(['b', 'a']);
  });
});
