import { inject, Injectable, signal } from '@angular/core';
import { catchError, concat, concatMap, EMPTY, last, map, Observable, of, Subject, switchMap, tap } from 'rxjs';
import { Confetti } from '../../shared/confetti';
import { ApiService } from '../api/api.service';
import { AuthStore } from '../auth/auth.store';
import { injectTranslator } from '../i18n';
import { injectNotify } from '../notify';
import { guessNext, isAired, isWatched, LoadedSeasons } from './episodes';

type Key = `${Model.Http.MediaType}:${number}`;
/** A title added from the results: on its way to the server, or written. */
export type AddState = 'saving' | 'saved';

/** What a write to a show changes: its tracking, its seasons' counts and the episode to watch next guessed from them. */
type ShowState = Pick<Model.Http.Show, 'tracking' | 'next_episode' | 'seasons'>;
/** An episode as a write needs it: its id, and its season whose count changes. */
export type EpisodeRef = Pick<Model.Http.Episode, 'id' | 'season_number'>;

interface Write {
  request: () => Observable<unknown>;
  settle: (succeeded: boolean, value?: unknown) => void;
}

/** Statuses a show leaves only when an episode is marked or the show is resumed. */
const SET_ASIDE: readonly Model.Http.TrackingStatus[] = ['stopped', 'watch_later'];
/** Statuses a marked episode turns into watching. */
const NOT_IN_PROGRESS: readonly Model.Http.TrackingStatus[] = [...SET_ASIDE, 'not_started'];
/** The API's limit of episode ids per request. */
const MAX_EPISODES_PER_REQUEST = 2000;

/** A view of the library: shows or movies, in an order, with one status or all. */
export interface LibraryQuery {
  mediaType: Model.Http.MediaType;
  sort?: Model.Http.LibrarySort;
  status?: Model.Http.TrackingStatus | null;
}

/** Confetti when the server says a show became finished. */
function celebrate(confetti: Confetti) {
  return (before: Model.Http.ShowTracking | null | undefined, saved: Model.Http.ShowTracking | null) => {
    if (before?.status !== 'finished' && saved?.status === 'finished') confetti.launch();
  };
}

export function libraryKey({ mediaType, sort = 'last_watched', status = null }: LibraryQuery): string {
  return `${mediaType}:${sort}:${status ?? 'all'}`;
}

export function resultKey(mediaType: Model.Http.MediaType, tmdbId: number): Key {
  return `${mediaType}:${tmdbId}`;
}

/**
 * Shows, movies and the library, with optimistic writes: a tap updates the store at once, then its request is queued
 * behind the earlier writes to the same item. The server's answer becomes the item's confirmed value; on an error,
 * when no later write to that item is queued, the item goes back to its confirmed value and a snackbar says so.
 * Each write returns a promise of whether the server accepted it. When the server says a show became finished, from
 * wherever its episodes were marked, confetti falls.
 */
@Injectable({ providedIn: 'root' })
export class TrackingStore {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthStore);
  private readonly confetti = inject(Confetti);
  private readonly notify = injectNotify();
  private readonly translate = injectTranslator('app');

  private readonly $shows = signal<Record<number, Model.Http.Show>>({});
  private readonly $movies = signal<Record<number, Model.Http.Movie>>({});
  private readonly $library = signal<Record<string, Model.Http.LibraryItem[]>>({});
  private readonly $episodes = signal<Record<number, LoadedSeasons>>({});
  private readonly $added = signal<Partial<Record<Key, AddState>>>({});
  private readonly showsAdded = new Subject<number>();
  private readonly queues = new Map<Key, Subject<Write>>();
  private readonly pending = new Map<Key, number>();
  private readonly confirmed = new Map<Key, unknown>();

  /** Loaded shows by TMDB id. */
  readonly shows = this.$shows.asReadonly();
  /** Loaded seasons' episodes, by TMDB id then season number. */
  readonly episodes = this.$episodes.asReadonly();
  /** Loaded movies by TMDB id. */
  readonly movies = this.$movies.asReadonly();
  /** The last library loaded for each query, by `libraryKey`. */
  readonly library = this.$library.asReadonly();
  /**
   * Titles added from search or trending results, by `resultKey`: saving at once, saved once the server wrote it,
   * absent again if the server refused.
   */
  readonly added = this.$added.asReadonly();
  /** The TMDB id of each show the server added to the library from the results. */
  readonly showAdded$ = this.showsAdded.asObservable();

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

  /** A season's episodes, asked of the server the first time. */
  loadSeason(tmdbId: number, seasonNumber: number): Observable<Model.Http.Episode[]> {
    const loaded = this.$episodes()[tmdbId]?.[seasonNumber];
    if (loaded) return of(loaded);
    return this.api.catalog.season(tmdbId, seasonNumber).pipe(
      map(({ episodes }) => episodes),
      tap((episodes) =>
        this.$episodes.update((all) => ({ ...all, [tmdbId]: { ...all[tmdbId], [seasonNumber]: episodes } })),
      ),
    );
  }

  /**
   * Mark episodes watched now, or unmark them. The screen changes at once (marks, season counts, the episode to watch
   * next guessed from the loaded seasons); the ids go to the server in requests of at most MAX_EPISODES_PER_REQUEST.
   */
  setWatched(tmdbId: number, episodes: EpisodeRef[], watched: boolean): Promise<boolean> {
    if (episodes.length === 0) return Promise.resolve(true);
    return this.updateShow(
      tmdbId,
      (state) => this.marked(tmdbId, state, episodes, watched),
      () => this.sendMarks(tmdbId, episodes, watched),
      celebrate(this.confetti),
    );
  }

  /**
   * Mark a season's aired episodes watched, or unmark its watched ones. Its count changes at once; a season not loaded
   * yet is loaded before the marks are sent.
   */
  markSeason(tmdbId: number, seasonNumber: number, watched: boolean): Promise<boolean> {
    const now = new Date();
    const targets = (episodes: Model.Http.Episode[]) => {
      const show = this.$shows()[tmdbId] ?? { tracking: null };
      return episodes.filter((episode) =>
        watched ? isAired(episode, now, this.auth.$timeZone()) && !isWatched(show, episode) : isWatched(show, episode),
      );
    };
    const loaded = this.$episodes()[tmdbId]?.[seasonNumber];
    if (loaded) return this.setWatched(tmdbId, targets(loaded), watched);
    return this.updateShow(
      tmdbId,
      (state) => {
        const seasons = state.seasons.map((season) =>
          season.season_number === seasonNumber
            ? { ...season, watched_count: watched ? Math.max(season.watched_count, season.aired_count) : 0 }
            : season,
        );
        return this.marked(tmdbId, { ...state, seasons }, [], watched);
      },
      () =>
        this.loadSeason(tmdbId, seasonNumber).pipe(
          switchMap((episodes) => {
            const ids = targets(episodes);
            return ids.length ? this.sendMarks(tmdbId, ids, watched) : of(this.$shows()[tmdbId]?.tracking ?? null);
          }),
        ),
      celebrate(this.confetti),
    );
  }

  /** Add the show to the library or resume it (watching), put it aside (watch_later) or stop it. */
  trackShow(tmdbId: number, status: Model.Http.ShowTrackingChoice): Promise<boolean> {
    return this.updateShow(
      tmdbId,
      (state) => {
        const { tracking } = state;
        const watched = tracking?.watched ?? {};
        if (status !== 'watching') return { ...state, tracking: { status, watched }, next_episode: null };
        if (tracking && !SET_ASIDE.includes(tracking.status)) return state;
        const resumed: Model.Http.ShowTracking = {
          status: Object.keys(watched).length === 0 ? 'not_started' : 'watching',
          watched,
        };
        return { ...state, tracking: resumed, next_episode: this.guess(tmdbId, resumed, state) ?? null };
      },
      () => this.api.tracking.trackShow(tmdbId, status),
    );
  }

  untrackShow(tmdbId: number): Promise<boolean> {
    this.forgetAdded('tv', tmdbId);
    return this.updateShow(
      tmdbId,
      (state) => ({ ...state, tracking: null, next_episode: null }),
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
    this.forgetAdded('movie', tmdbId);
    return this.updateMovieTracking(
      tmdbId,
      () => null,
      () => this.api.tracking.untrackMovie(tmdbId).pipe(map(() => null)),
    );
  }

  /** A title removed from the library is no longer shown as added in the results. */
  private forgetAdded(mediaType: Model.Http.MediaType, tmdbId: number): void {
    const key = resultKey(mediaType, tmdbId);
    this.$added.update(({ [key]: _, ...others }) => others);
  }

  /**
   * Add a title seen only among search or trending results: a show to watch, a movie to watch later. The server
   * writes only titles in its catalog, so the title's page is loaded first.
   */
  async addFromResults(mediaType: Model.Http.MediaType, tmdbId: number): Promise<boolean> {
    const key = resultKey(mediaType, tmdbId);
    this.$added.update((added) => ({ ...added, [key]: 'saving' }));
    const saved = await (mediaType === 'tv'
      ? this.updateShow(
          tmdbId,
          (state) => (state.tracking ? state : { ...state, tracking: { status: 'not_started', watched: {} } }),
          () => this.api.catalog.show(tmdbId).pipe(switchMap(() => this.api.tracking.trackShow(tmdbId, 'watching'))),
        )
      : this.updateMovieTracking(
          tmdbId,
          (tracking) => tracking ?? { status: 'watch_later', watched_at: null },
          () => this.api.catalog.movie(tmdbId).pipe(switchMap(() => this.api.tracking.trackMovie(tmdbId, false))),
        ));
    this.$added.update(({ [key]: _, ...others }) => (saved ? { ...others, [key]: 'saved' } : others));
    if (saved && mediaType === 'tv') this.showsAdded.next(tmdbId);
    return saved;
  }

  /** The show after marking or unmarking `episodes`: marks, status, season counts and the guessed next episode. */
  private marked(tmdbId: number, state: ShowState, episodes: EpisodeRef[], watched: boolean): ShowState {
    const { tracking } = state;
    if (!tracking && !watched) return state;
    const marks = { ...tracking?.watched };
    const changes = new Map<number, number>();
    const now = new Date().toISOString();
    for (const { id, season_number } of episodes) {
      if (watched === !!marks[id]) continue;
      if (watched) marks[id] = now;
      else delete marks[id];
      changes.set(season_number, (changes.get(season_number) ?? 0) + (watched ? 1 : -1));
    }
    let status = tracking?.status ?? 'watching';
    if (watched && (!tracking || NOT_IN_PROGRESS.includes(status))) status = 'watching';
    if (!watched && Object.keys(marks).length === 0 && !SET_ASIDE.includes(status)) status = 'not_started';
    const seasons = state.seasons.map((season) => {
      const change = changes.get(season.season_number);
      return change ? { ...season, watched_count: Math.max(0, season.watched_count + change) } : season;
    });
    const next: Model.Http.ShowTracking = { status, watched: marks };
    const guessed = this.guess(tmdbId, next, { ...state, seasons });
    return { tracking: next, seasons, next_episode: guessed === undefined ? state.next_episode : guessed };
  }

  /** The episode to watch next with `tracking`, from the loaded seasons; undefined when they cannot say. */
  private guess(
    tmdbId: number,
    tracking: Model.Http.ShowTracking,
    state: ShowState,
  ): Model.Http.NextEpisode | null | undefined {
    const show = this.$shows()[tmdbId];
    if (!show) return undefined;
    const loaded = this.$episodes()[tmdbId] ?? {};
    return guessNext({ ...show, ...state, tracking }, loaded, new Date(), this.auth.$timeZone());
  }

  /** The marks in requests of at most MAX_EPISODES_PER_REQUEST, one after the other; the last answer is the show's. */
  private sendMarks(
    tmdbId: number,
    episodes: EpisodeRef[],
    watched: boolean,
  ): Observable<Model.Http.ShowTracking | null> {
    const ids = episodes.map(({ id }) => id);
    const requests: Observable<Model.Http.ShowTracking | null>[] = [];
    for (let start = 0; start < ids.length; start += MAX_EPISODES_PER_REQUEST)
      requests.push(this.api.tracking.setWatched(tmdbId, ids.slice(start, start + MAX_EPISODES_PER_REQUEST), watched));
    return concat(...requests).pipe(last());
  }

  /**
   * `saved` runs on each answer with the tracking confirmed before it and the one the server sent. Once no write to the
   * show is left, the show is loaded again: the server's next episode and counts replace the guesses.
   */
  private updateShow(
    tmdbId: number,
    next: (state: ShowState) => ShowState,
    request: () => Observable<Model.Http.ShowTracking | null>,
    saved?: (before: Model.Http.ShowTracking | null | undefined, after: Model.Http.ShowTracking | null) => void,
  ): Promise<boolean> {
    const set = (state: ShowState) =>
      this.$shows.update((all) => (all[tmdbId] ? { ...all, [tmdbId]: { ...all[tmdbId], ...state } } : all));
    const loaded = this.$shows()[tmdbId];
    const current: ShowState = {
      tracking: loaded?.tracking ?? null,
      next_episode: loaded?.next_episode ?? null,
      seasons: loaded?.seasons ?? [],
    };
    set(next(current));
    return this.write<ShowState>(
      `tv:${tmdbId}`,
      current,
      set,
      () => request().pipe(map((tracking) => ({ ...this.showState(tmdbId), tracking }))),
      saved && ((before, after) => saved(before?.tracking, after.tracking)),
    ).then((succeeded) => {
      this.refresh(tmdbId);
      return succeeded;
    });
  }

  private showState(tmdbId: number): ShowState {
    const show = this.$shows()[tmdbId];
    return { tracking: show?.tracking ?? null, next_episode: show?.next_episode ?? null, seasons: show?.seasons ?? [] };
  }

  /** Load a loaded show again, unless a write to it is queued, whose answer would then be undone on screen. */
  private refresh(tmdbId: number): void {
    const idle = () => (this.pending.get(`tv:${tmdbId}`) ?? 0) === 0;
    if (!this.$shows()[tmdbId] || !idle()) return;
    this.api.catalog.show(tmdbId).subscribe({
      next: (show) => idle() && this.$shows.update((all) => ({ ...all, [tmdbId]: show })),
      error: () => undefined,
    });
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
  private write<T>(
    key: Key,
    before: T,
    set: (value: T) => void,
    request: () => Observable<T>,
    saved?: (before: T | undefined, after: T) => void,
  ): Promise<boolean> {
    const pending = this.pending.get(key) ?? 0;
    if (pending === 0) this.confirmed.set(key, before);
    this.pending.set(key, pending + 1);
    return new Promise((resolve) =>
      this.queueFor(key).next({
        request,
        settle: (succeeded, value) => {
          const left = this.pending.get(key)! - 1;
          this.pending.set(key, left);
          if (succeeded) {
            saved?.(this.confirmed.get(key) as T | undefined, value as T);
            this.confirmed.set(key, value);
          }
          resolve(succeeded);
          if (left > 0) return;
          set(this.confirmed.get(key) as T);
          if (!succeeded) this.notify(this.translate('app.tracking.saveFailed'));
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
