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
    store.trackShow(7, true);
    http.expectOne('/api/shows/7/tracking').flush({ status: 'stopped', watched: { a: 'x' } });

    store.trackShow(7, false);

    expect(tracking()?.status).toBe('watching');
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
});
