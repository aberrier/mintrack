import { inject, Injectable, signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, concatMap, EMPTY, map, Observable, Subject, tap } from 'rxjs';
import { ApiService } from '../api/api.service';
import { injectTranslator } from '../i18n';

type Key = `${Model.Http.MediaType}:${number}`;

interface Write {
  request: () => Observable<unknown>;
  settle: (succeeded: boolean, value?: unknown) => void;
}

/**
 * Shows, movies and the library, with optimistic writes: a tap updates the store at once, then its request is queued
 * behind the earlier writes to the same item. The server's answer becomes the item's confirmed value; on an error,
 * when no later write to that item is queued, the item goes back to its confirmed value and a snackbar says so.
 */
@Injectable({ providedIn: 'root' })
export class TrackingStore {
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = injectTranslator('app');

  private readonly $shows = signal<Record<number, Model.Http.Show>>({});
  private readonly $movies = signal<Record<number, Model.Http.Movie>>({});
  private readonly $library = signal<Partial<Record<Model.Http.MediaType, Model.Http.LibraryItem[]>>>({});
  private readonly queues = new Map<Key, Subject<Write>>();
  private readonly pending = new Map<Key, number>();
  private readonly confirmed = new Map<Key, unknown>();

  /** Loaded shows by TMDB id. */
  readonly shows = this.$shows.asReadonly();
  /** Loaded movies by TMDB id. */
  readonly movies = this.$movies.asReadonly();
  /** The last library loaded for each media type. */
  readonly library = this.$library.asReadonly();

  loadShow(tmdbId: number): Observable<Model.Http.Show> {
    return this.api.catalog.show(tmdbId).pipe(tap((show) => this.$shows.update((all) => ({ ...all, [tmdbId]: show }))));
  }

  loadMovie(tmdbId: number): Observable<Model.Http.Movie> {
    return this.api.catalog
      .movie(tmdbId)
      .pipe(tap((movie) => this.$movies.update((all) => ({ ...all, [tmdbId]: movie }))));
  }

  loadLibrary(mediaType: Model.Http.MediaType): Observable<Model.Http.LibraryItem[]> {
    return this.api.tracking
      .library(mediaType)
      .pipe(tap((items) => this.$library.update((all) => ({ ...all, [mediaType]: items }))));
  }

  /** Mark episodes watched now, or unmark them. */
  setWatched(tmdbId: number, episodeIds: string[], watched: boolean): void {
    this.updateShowTracking(
      tmdbId,
      (tracking) => {
        const marks = { ...tracking?.watched };
        const now = new Date().toISOString();
        for (const id of episodeIds) {
          if (watched) marks[id] ??= now;
          else delete marks[id];
        }
        if (!tracking && !watched) return null;
        const status = !tracking || (watched && tracking.status === 'stopped') ? 'watching' : tracking.status;
        return { status, watched: marks };
      },
      () => this.api.tracking.setWatched(tmdbId, episodeIds, watched),
    );
  }

  /** Add the show to the library, stop it or resume it. */
  trackShow(tmdbId: number, stopped: boolean): void {
    this.updateShowTracking(
      tmdbId,
      (tracking) => {
        const watched = tracking?.watched ?? {};
        if (stopped) return { status: 'stopped', watched };
        if (tracking && tracking.status !== 'stopped') return tracking;
        return { status: Object.keys(watched).length > 0 ? 'watching' : 'watch_later', watched };
      },
      () => this.api.tracking.trackShow(tmdbId, stopped),
    );
  }

  untrackShow(tmdbId: number): void {
    this.updateShowTracking(
      tmdbId,
      () => null,
      () => this.api.tracking.untrackShow(tmdbId).pipe(map(() => null)),
    );
  }

  /** Add the movie to the library, watched now or to watch later. */
  trackMovie(tmdbId: number, watched: boolean): void {
    this.updateMovieTracking(
      tmdbId,
      (tracking) => ({
        status: watched ? 'watched' : 'watch_later',
        watched_at: watched ? (tracking?.watched_at ?? new Date().toISOString()) : null,
      }),
      () => this.api.tracking.trackMovie(tmdbId, watched),
    );
  }

  untrackMovie(tmdbId: number): void {
    this.updateMovieTracking(
      tmdbId,
      () => null,
      () => this.api.tracking.untrackMovie(tmdbId).pipe(map(() => null)),
    );
  }

  private updateShowTracking(
    tmdbId: number,
    next: (tracking: Model.Http.ShowTracking | null) => Model.Http.ShowTracking | null,
    request: () => Observable<Model.Http.ShowTracking | null>,
  ): void {
    const set = (tracking: Model.Http.ShowTracking | null) =>
      this.$shows.update((all) => (all[tmdbId] ? { ...all, [tmdbId]: { ...all[tmdbId], tracking } } : all));
    const current = this.$shows()[tmdbId]?.tracking ?? null;
    set(next(current));
    this.write(`tv:${tmdbId}`, current, set, request);
  }

  private updateMovieTracking(
    tmdbId: number,
    next: (tracking: Model.Http.MovieTracking | null) => Model.Http.MovieTracking | null,
    request: () => Observable<Model.Http.MovieTracking | null>,
  ): void {
    const set = (tracking: Model.Http.MovieTracking | null) =>
      this.$movies.update((all) => (all[tmdbId] ? { ...all, [tmdbId]: { ...all[tmdbId], tracking } } : all));
    const current = this.$movies()[tmdbId]?.tracking ?? null;
    set(next(current));
    this.write(`movie:${tmdbId}`, current, set, request);
  }

  /** Queue `request` behind the earlier writes to the same item; `before` is the item's value before this write. */
  private write<T>(key: Key, before: T, set: (value: T) => void, request: () => Observable<T>): void {
    const pending = this.pending.get(key) ?? 0;
    if (pending === 0) this.confirmed.set(key, before);
    this.pending.set(key, pending + 1);
    this.queueFor(key).next({
      request,
      settle: (succeeded, value) => {
        const left = this.pending.get(key)! - 1;
        this.pending.set(key, left);
        if (succeeded) this.confirmed.set(key, value);
        if (left > 0) return;
        set(this.confirmed.get(key) as T);
        if (!succeeded) this.snackBar.open(this.translate('app.tracking.saveFailed'), undefined, { duration: 4000 });
      },
    });
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
