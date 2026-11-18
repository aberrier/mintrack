import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TrackingStore } from './tracking.store';

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
};

describe('TrackingStore', () => {
  let store: TrackingStore;
  let http: HttpTestingController;
  let snackBar: { open: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    snackBar = { open: vi.fn() };
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: MatSnackBar, useValue: snackBar }],
    });
    store = TestBed.inject(TrackingStore);
    http = TestBed.inject(HttpTestingController);
    store.loadShow(7).subscribe();
    http.expectOne('/api/shows/7').flush(SHOW);
  });

  const tracking = () => store.shows()[7].tracking;

  it('shows a tap before the server answers, then the server answer', () => {
    store.setWatched(7, ['a'], true);

    expect(tracking()?.status).toBe('watching');
    expect(Object.keys(tracking()!.watched)).toEqual(['a']);

    http.expectOne('/api/shows/7/watched').flush({ status: 'up_to_date', watched: { a: '2026-01-01T00:00:00Z' } });
    expect(tracking()).toEqual({ status: 'up_to_date', watched: { a: '2026-01-01T00:00:00Z' } });
  });

  it('sends writes to the same show one after the other', () => {
    store.setWatched(7, ['a'], true);
    store.setWatched(7, ['b'], true);

    const first = http.expectOne('/api/shows/7/watched');
    http.expectNone('/api/shows/7/watched');
    first.flush({ status: 'watching', watched: { a: 'x' } });

    // The first answer must not hide the second tap, still queued.
    expect(Object.keys(tracking()!.watched).sort()).toEqual(['a', 'b']);
    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x', b: 'y' } });
    expect(tracking()?.watched).toEqual({ a: 'x', b: 'y' });
  });

  it('shows a resumed show as watching at once', () => {
    store.setWatched(7, ['a'], true);
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

    void store.setWatched(7, ['a'], true);

    expect(tracking()?.status).toBe('watching');
  });

  it('tells each caller whether the server accepted its write', async () => {
    const accepted = store.setWatched(7, ['a'], true);
    const refused = store.setWatched(7, ['b'], true);

    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x' } });
    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });

    expect(await accepted).toBe(true);
    expect(await refused).toBe(false);
  });

  it('goes back to the last confirmed value and says so when the last queued write fails', () => {
    store.setWatched(7, ['a'], true);
    http.expectOne('/api/shows/7/watched').flush({ status: 'watching', watched: { a: 'x' } });
    store.setWatched(7, ['b'], true);
    store.setWatched(7, ['c'], true);

    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });
    expect(snackBar.open).not.toHaveBeenCalled();
    http.expectOne('/api/shows/7/watched').flush('down', { status: 500, statusText: 'Server Error' });

    expect(tracking()).toEqual({ status: 'watching', watched: { a: 'x' } });
    expect(snackBar.open).toHaveBeenCalledOnce();
  });

  it('shows a long season marked at once, and sends it in requests of at most 2000 ids, one after the other', async () => {
    const ids = Array.from({ length: 4500 }, (_, index) => `e${index}`);

    const saved = store.setWatched(7, ids, true);

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

  it('keeps each library view apart, by type, sort and progress', () => {
    store.loadLibrary({ mediaType: 'tv', sort: 'title', status: 'finished' }).subscribe();
    const request = http.expectOne((r) => r.url === '/api/library');

    expect(request.request.params.toString()).toBe('media_type=tv&sort=title&status=finished');
    request.flush([]);
    expect(store.library()['tv:title:finished']).toEqual([]);
    expect(store.library()['tv:last_watched:all']).toBeUndefined();
  });
});
