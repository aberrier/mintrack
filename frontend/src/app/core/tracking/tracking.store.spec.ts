import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Confetti } from '../../shared/confetti';
import { Haptics } from '../haptics';
import { EpisodeRef, TrackingStore } from './tracking.store';

const SHOW: Model.Http.Show = {
  tmdb_id: 7,
  title: 'Show',
  overview: '',
  poster_path: null,
  release_date: null,
  tmdb_status: 'Returning Series',
  backdrop_path: null,
  network: null,
  runtime: null,
  seasons: [],
  tracking: null,
  next_episode: null,
};

const ref = (id: string): EpisodeRef => ({ id, season_number: 1 });

const aired = (id: string, number: number): Model.Http.Episode => ({
  id,
  season_number: 1,
  episode_number: number,
  title: '',
  air_date: '2020-01-01',
  airstamp: null,
});

const SEASON: Model.Http.Season = {
  season_number: 1,
  title: 'Season 1',
  episode_count: 3,
  watched_count: 1,
  aired_count: 3,
};

describe('TrackingStore', () => {
  let store: TrackingStore;
  let http: HttpTestingController;
  let snackBar: { open: ReturnType<typeof vi.fn> };
  let haptics: { tap: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    snackBar = { open: vi.fn() };
    haptics = { tap: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MatSnackBar, useValue: snackBar },
        { provide: Confetti, useValue: { launch: vi.fn() } },
        { provide: Haptics, useValue: haptics },
      ],
    });
    store = TestBed.inject(TrackingStore);
    http = TestBed.inject(HttpTestingController);
    store.loadShow(7).subscribe();
    http.expectOne('/api/shows/7').flush(SHOW);
  });

  const tracking = () => store.shows()[7].tracking;

  /** A show of three aired episodes, the first watched, its season loaded or not. */
  function loadShow8(withEpisodes: boolean): void {
    store.loadShow(8).subscribe();
    http.expectOne('/api/shows/8').flush({
      ...SHOW,
      tmdb_id: 8,
      seasons: [SEASON],
      tracking: { status: 'watching', watched: { a: 'x' } },
      next_episode: { ...aired('b', 2), remaining: 1 },
    });
    if (!withEpisodes) return;
    store.loadSeason(8, 1).subscribe();
    http
      .expectOne('/api/shows/8/seasons/1')
      .flush({ season_number: 1, episodes: [aired('a', 1), aired('b', 2), aired('c', 3)] });
  }

  it('shows a tap before the server answers, then the server answer', () => {
    store.setWatched(7, [ref('a')], true);

    expect(tracking()?.status).toBe('watching');
    expect(Object.keys(tracking()!.watched)).toEqual(['a']);

    http.expectOne('/api/shows/7/watched').flush({ status: 'up_to_date', watched: { a: '2026-01-01T00:00:00Z' } });
    expect(tracking()).toEqual({ status: 'up_to_date', watched: { a: '2026-01-01T00:00:00Z' } });
  });

  it('vibrates on adding a show and on each mark or unmark, not on putting it aside', () => {
    void store.trackShow(7, 'watching');
    http.expectOne('/api/shows/7/tracking').flush({ status: 'not_started', watched: {} });
    void store.trackShow(7, 'stopped');
    expect(haptics.tap).toHaveBeenCalledOnce();

    void store.setWatched(7, [ref('a')], true);
    void store.setWatched(7, [ref('a')], false);

    expect(haptics.tap).toHaveBeenCalledTimes(3);
  });

  it('says a show is saving from the tap until it is loaded again', async () => {
    void store.trackShow(7, 'watching');
    expect(store.saving()[7]).toBe(true);

    http.expectOne('/api/shows/7/tracking').flush({ status: 'not_started', watched: {} });
    await new Promise((resolve) => setTimeout(resolve));
    expect(store.saving()[7]).toBe(true);
    http.expectOne('/api/shows/7').flush({ ...SHOW, tracking: { status: 'not_started', watched: {} } });

    expect(store.saving()[7]).toBeUndefined();
  });

  it('sends writes to the same show one after the other', () => {
    store.setWatched(7, [ref('a')], true);
    store.setWatched(7, [ref('b')], true);

    const first = http.expectOne('/api/shows/7/watched');
    http.expectNone('/api/shows/7/watched');
    first.flush({ status: 'watching', watched: { a: 'x' } });

    // The first answer must not hide the second tap, still queued.
    expect(Object.keys(tracking()!.watched).sort()).toEqual(['a', 'b']);
    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x', b: 'y' } });
    expect(tracking()?.watched).toEqual({ a: 'x', b: 'y' });
  });

  it('shows a resumed show as watching at once, and one with nothing watched as not started', () => {
    void store.trackShow(7, 'watching');
    expect(tracking()?.status).toBe('not_started');
    http.expectOne('/api/shows/7/tracking').flush({ status: 'not_started', watched: {} });

    store.setWatched(7, [ref('a')], true);
    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x' } });
    void store.trackShow(7, 'stopped');
    http.expectOne('/api/shows/7/tracking').flush({ status: 'stopped', watched: { a: 'x' } });

    void store.trackShow(7, 'watching');

    expect(tracking()?.status).toBe('watching');
  });

  it('puts a show aside at once, and a marked episode brings it back', () => {
    void store.trackShow(7, 'watch_later');
    expect(tracking()?.status).toBe('watch_later');
    http.expectOne('/api/shows/7/tracking').flush({ status: 'watch_later', watched: {} });

    void store.setWatched(7, [ref('a')], true);

    expect(tracking()?.status).toBe('watching');
  });

  it('tells each caller whether the server accepted its write', async () => {
    const accepted = store.setWatched(7, [ref('a')], true);
    const refused = store.setWatched(7, [ref('b')], true);

    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x' } });
    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });

    expect(await accepted).toBe(true);
    expect(await refused).toBe(false);
  });

  it('goes back to the last confirmed value and says so when the last queued write fails', () => {
    store.setWatched(7, [ref('a')], true);
    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x' } });
    store.setWatched(7, [ref('b')], true);
    store.setWatched(7, [ref('c')], true);

    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });
    expect(snackBar.open).not.toHaveBeenCalled();
    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });

    expect(tracking()).toEqual({ status: 'watching', watched: { a: 'x' } });
    expect(snackBar.open).toHaveBeenCalledOnce();
  });

  it('shows a long season marked at once, and sends it in requests of at most 2000 ids, one after the other', async () => {
    const ids = Array.from({ length: 4500 }, (_, index) => `e${index}`);

    const saved = store.setWatched(7, ids.map(ref), true);

    expect(Object.keys(tracking()!.watched)).toHaveLength(4500);
    const sizes: number[] = [];
    for (let left = 3; left > 0; left--) {
      const request = http.expectOne('/api/shows/7/watched');
      http.expectNone('/api/shows/7/watched');
      sizes.push((request.request.body as { episode_ids: string[] }).episode_ids.length);
      request.flush({ status: 'watching', watched: Object.fromEntries(ids.map((id) => [id, 'x'])) });
    }
    expect(sizes).toEqual([2000, 2000, 500]);
    expect(await saved).toBe(true);
  });

  it('guesses the next episode and the season count at once, and puts both back on an error', () => {
    loadShow8(true);

    store.setWatched(8, [aired('b', 2)], true);
    expect(store.shows()[8].next_episode).toMatchObject({ id: 'c', remaining: 0 });
    expect(store.shows()[8].seasons[0].watched_count).toBe(2);

    http.expectOne('/api/shows/8/watched').flush('down', { status: 500, statusText: 'Server Error' });
    expect(store.shows()[8].next_episode).toMatchObject({ id: 'b', remaining: 1 });
    expect(store.shows()[8].seasons[0].watched_count).toBe(1);
    expect(store.shows()[8].tracking?.watched).toEqual({ a: 'x' });
  });

  it('loads the show again once its writes are saved, for the server’s next episode', async () => {
    loadShow8(false);

    const saved = store.setWatched(8, [aired('b', 2)], true);
    http.expectOne('/api/shows/8/watched').flush({ status: 'watching', watched: { a: 'x', b: 'y' } });
    await saved;

    http.expectOne('/api/shows/8').flush({
      ...SHOW,
      tmdb_id: 8,
      seasons: [{ ...SEASON, watched_count: 2 }],
      tracking: { status: 'watching', watched: { a: 'x', b: 'y' } },
      next_episode: { ...aired('c', 3), remaining: 0 },
    });
    expect(store.shows()[8].next_episode?.id).toBe('c');
  });

  it('marks a season not loaded at once by its count, then loads it and sends its aired episodes left', () => {
    loadShow8(false);

    void store.markSeason(8, 1, true);

    expect(store.shows()[8].seasons[0].watched_count).toBe(3);
    http
      .expectOne('/api/shows/8/seasons/1')
      .flush({ season_number: 1, episodes: [aired('a', 1), aired('b', 2), aired('c', 3)] });
    const request = http.expectOne('/api/shows/8/watched');
    expect(request.request.body).toEqual({ episode_ids: ['b', 'c'], watched: true });
  });

  it('asks the server for a season only once', () => {
    loadShow8(true);

    store.loadSeason(8, 1).subscribe();

    http.expectNone('/api/shows/8/seasons/1');
    expect(store.episodes()[8][1]).toHaveLength(3);
  });

  it('marks a title added from the results at once, and unmarks it when the server refuses', async () => {
    const added = store.addFromResults('movie', 9);

    expect(store.added()['movie:9']).toBe('saving');
    http.expectOne('/api/movies/9').flush('down', { status: 500, statusText: 'Server Error' });

    expect(await added).toBe(false);
    expect(store.added()['movie:9']).toBeUndefined();
  });

  it('says when a show added from the results is saved', async () => {
    const shows: number[] = [];
    store.showAdded$.subscribe((tmdbId) => shows.push(tmdbId));
    const added = store.addFromResults('tv', 7);

    http.expectOne('/api/shows/7').flush(SHOW);
    expect(store.added()['tv:7']).toBe('saving');
    expect(shows).toEqual([]);
    http.expectOne('/api/shows/7/tracking').flush({ status: 'not_started', watched: {} });

    expect(await added).toBe(true);
    expect(store.added()['tv:7']).toBe('saved');
    expect(shows).toEqual([7]);
  });

  it('no longer shows a title as added once it is removed from the library', async () => {
    const added = store.addFromResults('tv', 7);
    http.expectOne('/api/shows/7').flush(SHOW);
    http.expectOne('/api/shows/7/tracking').flush({ status: 'not_started', watched: {} });
    await added;

    const removed = store.untrackShow(7);

    expect(store.added()['tv:7']).toBeUndefined();
    http.expectOne('/api/shows/7/tracking').flush(null);
    expect(await removed).toBe(true);
  });

  it('keeps each library view apart, by type, sort and progress', () => {
    store.loadLibrary({ mediaType: 'tv', sort: 'title', status: 'finished' }).subscribe();
    const request = http.expectOne((r) => r.url === '/api/library');

    expect(request.request.params.toString()).toBe('media_type=tv&sort=title&status=finished');
    request.flush([]);
    expect(store.library()['tv:title:finished']).toEqual([]);
    expect(store.library()['tv:last_watched:all']).toBeUndefined();
  });
});
