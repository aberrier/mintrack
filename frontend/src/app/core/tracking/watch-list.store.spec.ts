import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { WatchListStore } from './watch-list.store';

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
    {
      season_number: 1,
      title: '',
      episodes: [episode('a', 1, 1, '2026-01-01'), episode('b', 1, 2, '2026-01-08'), episode('c', 1, 3, '2026-01-15')],
    },
    { season_number: 2, title: '', episodes: [episode('d', 2, 1, '2099-01-01')] },
  ],
  tracking: { status: 'watching', watched: { a: '2026-06-01T00:00:00Z' } },
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
  };
}

describe('WatchListStore', () => {
  let store: WatchListStore;
  let http: HttpTestingController;
  let snackBar: { open: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    snackBar = { open: vi.fn() };
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: MatSnackBar, useValue: snackBar }],
    });
    store = TestBed.inject(WatchListStore);
    http = TestBed.inject(HttpTestingController);
  });

  function loadList(episodes: Model.Http.WatchListEpisode[]): void {
    store.load().subscribe();
    http.expectOne('/api/watch-list').flush({ episodes });
  }

  it('moves a checked card to the next episode before the server answers', () => {
    loadList([card()]);

    store.check(store.episodes()![0], NOW);
    http.expectOne('/api/shows/7').flush(SHOW);

    const [next] = store.episodes()!;
    expect([next.episode_id, next.season_number, next.episode_number, next.remaining]).toEqual(['c', 1, 3, 0]);
    const write = http.expectOne('/api/shows/7/watched');
    expect(write.request.body).toEqual({ episode_ids: ['b'], watched: true });
  });

  it('takes the card out when the show is up to date, without loading the show', () => {
    loadList([card({ episode_id: 'c', episode_number: 3, remaining: 0 })]);

    store.check(store.episodes()![0], NOW);

    expect(store.episodes()).toEqual([]);
  });

  it('moves a show not watched for a while to the top of Watch next', () => {
    loadList([card({ tmdb_id: 1, episode_id: 'x', section: 'next' }), card({ section: 'dormant' })]);

    store.check(store.episodes()![1], NOW);
    http.expectOne('/api/shows/7').flush(SHOW);

    expect(store.episodes()!.map((e) => [e.tmdb_id, e.section])).toEqual([
      [7, 'next'],
      [1, 'next'],
    ]);
  });

  it('loads the list again and says so when the server refuses the check', async () => {
    loadList([card()]);

    store.check(store.episodes()![0], NOW);
    http.expectOne('/api/shows/7').flush(SHOW);
    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });
    await Promise.resolve();
    http.expectOne('/api/watch-list').flush({ episodes: [card()] });

    expect(store.episodes()![0].episode_id).toBe('b');
    expect(snackBar.open).toHaveBeenCalledWith('Your change could not be saved.', undefined, { duration: 4000 });
  });

  it('removes a card put aside or stopped at once', () => {
    loadList([card(), card({ tmdb_id: 8 })]);

    store.remove(store.episodes()![0], 'watch_later');
    store.remove(store.episodes()![0], 'stopped');

    expect(store.episodes()).toEqual([]);
    expect(http.expectOne('/api/shows/7/tracking').request.body).toEqual({ status: 'watch_later' });
    expect(http.expectOne('/api/shows/8/tracking').request.body).toEqual({ status: 'stopped' });
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
    loadList([card()]);
    store.loadOlderHistory();
    http.expectOne('/api/history').flush({ entries: [entry('a', '2026-06-01T00:00:00Z')], has_more: true });

    store.check(store.episodes()![0], NOW);
    http.expectOne('/api/shows/7').flush(SHOW);
    store.loadOlderHistory();
    http
      .expectOne((request) => request.url === '/api/history')
      .flush({ entries: [entry('b', NOW.toISOString())], has_more: false });

    expect(store.history().map((e) => e.id)).toEqual(['b', 'a']);
  });
});
