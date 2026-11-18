import { inject, Injectable, signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, concatMap, EMPTY, map, Observable, Subject, switchMap, tap } from 'rxjs';
import { ApiService } from '../api/api.service';
import { injectTranslator } from '../i18n';

type Key = `${Model.Http.MediaType}:${number}`;

interface Write {
  request: () => Observable<unknown>;
  settle: (succeeded: boolean, value?: unknown) => void;
}

/** Statuses a show leaves only when an episode is marked or the show is resumed. */
const SET_ASIDE: readonly Model.Http.TrackingStatus[] = ['stopped', 'watch_later'];
/** The API's limit of episode ids per request. */
export const MAX_EPISODES_PER_REQUEST = 2000;

/** A view of the library: shows or movies, in an order, with one status or all. */
export interface LibraryQuery {
  mediaType: Model.Http.MediaType;
  sort?: Model.Http.LibrarySort;
  status?: Model.Http.LibraryStatus | null;
}

export function libraryKey({ mediaType, sort = 'last_watched', status = null }: LibraryQuery): string {
  return `${mediaType}:${sort}:${status ?? 'all'}`;
}

/**
 * Shows, movies and the library, with optimistic writes: a tap updates the store at once, then its request is queued
 * behind the earlier writes to the same item. The server's answer becomes the item's confirmed value; on an error,
 * when no later write to that item is queued, the item goes back to its confirmed value and a snackbar says so.
 * Each write returns a promise of whether the server accepted it, for stores that show the same item elsewhere.
 */
@Injectable({ providedIn: 'root' })
export class TrackingStore {
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = injectTranslator('app');

  private readonly $shows = signal<Record<number, Model.Http.Show>>({});
  private readonly $movies = signal<Record<number, Model.Http.Movie>>({});
  private readonly $library = signal<Record<string, Model.Http.LibraryItem[]>>({});
  private readonly queues = new Map<Key, Subject<Write>>();
  private readonly pending = new Map<Key, number>();
  private readonly confirmed = new Map<Key, unknown>();

  /** Loaded shows by TMDB id. */
  readonly shows = this.$shows.asReadonly();
  /** Loaded movies by TMDB id. */
  readonly movies = this.$movies.asReadonly();
  /** The last library loaded for each query, by `libraryKey`. */
  readonly library = this.$library.asReadonly();

  loadShow(tmdbId: number): Observable<Model.Http.Show> {
    return this.api.catalog.show(tmdbId).pipe(tap((show) => this.$shows.update((all) => ({ ...all, [tmdbId]: show }))));
  }

  loadMovie(tmdbId: number): Observable<Model.Http.Movie> {
    return this.api.catalog
      .movie(tmdbId)
      .pipe(tap((movie) => this.$movies.update((all) => ({ ...all, [tmdbId]: movie }))));
  }

  loadLibrary(query: LibraryQuery): Observable<Model.Http.LibraryItem[]> {
    return this.api.tracking
      .library(query)
      .pipe(tap((items) => this.$library.update((all) => ({ ...all, [libraryKey(query)]: items }))));
  }

  /**
   * Mark episodes watched now, or unmark them. The screen changes at once; the ids go to the server in requests of at
   * most MAX_EPISODES_PER_REQUEST, each answer confirming what it saved.
   */
  setWatched(tmdbId: number, episodeIds: string[], watched: boolean): Promise<boolean> {
    const chunks: string[][] = [];
    for (let start = 0; start < episodeIds.length; start += MAX_EPISODES_PER_REQUEST)
      chunks.push(episodeIds.slice(start, start + MAX_EPISODES_PER_REQUEST));
    const marked = (tracking: Model.Http.ShowTracking | null): Model.Http.ShowTracking | null => {
      const marks = { ...tracking?.watched };
      const now = new Date().toISOString();
      for (const id of episodeIds) {
        if (watched) marks[id] ??= now;
        else delete marks[id];
      }
      if (!tracking && !watched) return null;
      const status = !tracking || (watched && SET_ASIDE.includes(tracking.status)) ? 'watching' : tracking.status;
      return { status, watched: marks };
    };
    const writes = chunks.map((ids, index) =>
      this.updateShowTracking(tmdbId, index === 0 ? marked : (tracking) => tracking, () =>
        this.api.tracking.setWatched(tmdbId, ids, watched),
      ),
    );
    return writes.length === 1 ? writes[0] : Promise.all(writes).then((results) => results.every(Boolean));
  }

  /** Add the show to the library or resume it (watching), put it aside (watch_later) or stop it. */
  trackShow(tmdbId: number, status: Model.Http.ShowTrackingChoice): Promise<boolean> {
    return this.updateShowTracking(
      tmdbId,
      (tracking) => {
        const watched = tracking?.watched ?? {};
        if (status !== 'watching') return { status, watched };
        if (tracking && !SET_ASIDE.includes(tracking.status)) return tracking;
        return { status: Object.keys(watched).length > 0 ? 'watching' : 'watch_later', watched };
      },
      () => this.api.tracking.trackShow(tmdbId, status),
    );
  }

  untrackShow(tmdbId: number): Promise<boolean> {
    return this.updateShowTracking(
      tmdbId,
      () => null,
      () => this.api.tracking.untrackShow(tmdbId).pipe(map(() => null)),
    );
  }

  /** Add the movie to the library, watched now or to watch later. */
  trackMovie(tmdbId: number, watched: boolean): Promise<boolean> {
    return this.updateMovieTracking(
      tmdbId,
      (tracking) => ({
        status: watched ? 'watched' : 'watch_later',
        watched_at: watched ? (tracking?.watched_at ?? new Date().toISOString()) : null,
      }),
      () => this.api.tracking.trackMovie(tmdbId, watched),
    );
  }

  untrackMovie(tmdbId: number): Promise<boolean> {
    return this.updateMovieTracking(
      tmdbId,
      () => null,
      () => this.api.tracking.untrackMovie(tmdbId).pipe(map(() => null)),
    );
  }

  /**
   * Add a title seen only among search or trending results: a show to watch, a movie to watch later. The server
   * writes only titles in its catalog, so the title's page is loaded first.
   */
  addFromResults(mediaType: Model.Http.MediaType, tmdbId: number): Promise<boolean> {
    if (mediaType === 'tv')
      return this.updateShowTracking(
        tmdbId,
        (tracking) => tracking ?? { status: 'watch_later', watched: {} },
        () => this.api.catalog.show(tmdbId).pipe(switchMap(() => this.api.tracking.trackShow(tmdbId, 'watching'))),
      );
    return this.updateMovieTracking(
      tmdbId,
      (tracking) => tracking ?? { status: 'watch_later', watched_at: null },
      () => this.api.catalog.movie(tmdbId).pipe(switchMap(() => this.api.tracking.trackMovie(tmdbId, false))),
    );
  }

  private updateShowTracking(
    tmdbId: number,
    next: (tracking: Model.Http.ShowTracking | null) => Model.Http.ShowTracking | null,
    request: () => Observable<Model.Http.ShowTracking | null>,
  ): Promise<boolean> {
    const set = (tracking: Model.Http.ShowTracking | null) =>
      this.$shows.update((all) => (all[tmdbId] ? { ...all, [tmdbId]: { ...all[tmdbId], tracking } } : all));
    const current = this.$shows()[tmdbId]?.tracking ?? null;
    set(next(current));
    return this.write(`tv:${tmdbId}`, current, set, request);
  }

  private updateMovieTracking(
    tmdbId: number,
    next: (tracking: Model.Http.MovieTracking | null) => Model.Http.MovieTracking | null,
    request: () => Observable<Model.Http.MovieTracking | null>,
  ): Promise<boolean> {
    const set = (tracking: Model.Http.MovieTracking | null) =>
      this.$movies.update((all) => (all[tmdbId] ? { ...all, [tmdbId]: { ...all[tmdbId], tracking } } : all));
    const current = this.$movies()[tmdbId]?.tracking ?? null;
    set(next(current));
    return this.write(`movie:${tmdbId}`, current, set, request);
  }

  /** Queue `request` behind the earlier writes to the same item; `before` is the item's value before this write. */
  private write<T>(key: Key, before: T, set: (value: T) => void, request: () => Observable<T>): Promise<boolean> {
    const pending = this.pending.get(key) ?? 0;
    if (pending === 0) this.confirmed.set(key, before);
    this.pending.set(key, pending + 1);
    return new Promise((resolve) =>
      this.queueFor(key).next({
        request,
        settle: (succeeded, value) => {
          const left = this.pending.get(key)! - 1;
          this.pending.set(key, left);
          if (succeeded) this.confirmed.set(key, value);
          resolve(succeeded);
          if (left > 0) return;
          set(this.confirmed.get(key) as T);
          if (!succeeded) this.snackBar.open(this.translate('app.tracking.saveFailed'), undefined, { duration: 4000 });
        },
      }),
    );
  }

  private queueFor(key: Key): Subject<Write> {
    let queue = this.queues.get(key);
    if (!queue) {
      queue = new Subject<Write>();
      queue
        .pipe(
          concatMap((write) =>
            write.request().pipe(
              tap((value) => write.settle(true, value)),
              catchError(() => {
                write.settle(false);
                return EMPTY;
              }),
            ),
          ),
        )
        .subscribe();
      this.queues.set(key, queue);
    }
    return queue;
  }
}
