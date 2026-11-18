import { inject, Injectable, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { ApiService } from '../api/api.service';
import { AuthStore } from '../auth/auth.store';
import { injectTranslator } from '../i18n';
import { injectNotify } from '../notify';
import { followingEpisode, isUpcoming } from './episodes';
import { TrackingStore } from './tracking.store';

export type HistoryState = 'idle' | 'loading' | 'failed' | 'done';
/** How a show leaves the watch list from its card. */
export type SetAside = Exclude<Model.Http.ShowTrackingChoice, 'watching'>;

/**
 * The watch list (the next episode of each show in progress) and the watch history above it.
 *
 * The list is a view derived from the shows: a tap changes it at once, the write goes through `TrackingStore` (which
 * says when it fails), and the list is loaded again from the server after a failure or when only the server knows the
 * following episode. A failed write puts the card back as it was.
 */
@Injectable({ providedIn: 'root' })
export class WatchListStore {
  private readonly api = inject(ApiService);
  private readonly tracking = inject(TrackingStore);
  private readonly auth = inject(AuthStore);
  private readonly notify = injectNotify();
  private readonly translate = injectTranslator('app');

  private readonly $episodes = signal<Model.Http.WatchListEpisode[] | undefined>(undefined);
  private readonly $history = signal<Model.Http.HistoryEntry[]>([]);
  private readonly $historyState = signal<HistoryState>('idle');
  private readonly $checking = signal<ReadonlySet<number>>(new Set());
  /** The oldest entry the server sent, from which the next page starts. */
  private cursor: Model.Http.HistoryEntry | null = null;
  private writes = 0;

  /** The last list loaded, with the taps since; most recently watched first. */
  readonly episodes = this.$episodes.asReadonly();
  /** Watched episodes and movies, newest first. */
  readonly history = this.$history.asReadonly();
  readonly historyState = this.$historyState.asReadonly();
  /** Shows whose card was checked and waits for the server to say what comes next. */
  readonly checking = this.$checking.asReadonly();

  load(): Observable<Model.Http.WatchListResponse> {
    return this.api.upcoming.watchList().pipe(
      tap((response) => {
        // A list loaded while taps are on their way would undo them on screen.
        if (this.writes > 0) return;
        this.$checking.set(new Set());
        this.$episodes.set(response.episodes);
      }),
    );
  }

  /**
   * Mark the card's episode watched now and move the card on: to the following episode when the loaded show says
   * which, else the card stays checked until the server's list comes back. A failure puts the card back as it was.
   */
  check(episode: Model.Http.WatchListEpisode, now = new Date()): void {
    const tmdbId = episode.tmdb_id;
    if (this.$checking().has(tmdbId)) return;
    const index = this.indexOf(tmdbId);
    this.writes++;
    const written = this.tracking.setWatched(
      tmdbId,
      [{ id: episode.episode_id, season_number: episode.season_number }],
      true,
    );
    const show = this.tracking.shows()[tmdbId];
    const fromShow =
      show &&
      followingEpisode(
        show,
        this.tracking.episodes()[tmdbId] ?? {},
        episode.season_number,
        episode.episode_number,
        now,
        this.auth.$timeZone(),
      );
    // The list's following episode may not have aired: then the show is up to date and its card leaves.
    const listed = episode.following;
    const fromList =
      listed &&
      (isUpcoming(listed, now, this.auth.$timeZone())
        ? null
        : { ...listed, remaining: Math.max(0, episode.remaining - 1) });
    const following = fromShow !== undefined ? fromShow : fromList;
    const waiting = following === undefined && episode.remaining > 0;
    if (waiting) this.$checking.update((checking) => new Set(checking).add(tmdbId));
    else
      this.replace(
        tmdbId,
        following
          ? {
              ...episode,
              episode_id: following.id,
              season_number: following.season_number,
              episode_number: following.episode_number,
              title: following.title,
              airstamp: following.airstamp,
              day: following.air_date,
              remaining: following.remaining,
              last_watched_at: now.toISOString(),
              section: 'next',
              // Only the server knows the episode after that one.
              following: undefined,
            }
          : null,
      );
    const entry = this.addToHistory(episode, now);
    void written.then((succeeded) => {
      if (!succeeded) this.restore(episode, index);
      this.settled(succeeded, entry, waiting);
    });
  }

  /** Take the show out of the watch list, to watch later or stopped, with a way back. */
  remove(episode: Model.Http.WatchListEpisode, status: SetAside): void {
    const index = this.indexOf(episode.tmdb_id);
    this.replace(episode.tmdb_id, null);
    this.writes++;
    void this.tracking.trackShow(episode.tmdb_id, status).then((succeeded) => this.settled(succeeded, null, false));
    this.notify(
      this.translate(status === 'watch_later' ? 'app.watchList.movedLater' : 'app.watchList.stopped'),
      this.translate('app.watchList.undo'),
    )
      .onAction()
      .subscribe(() => this.undo(episode, index));
  }

  /** Load the next page of history, older than what is shown. */
  loadOlderHistory(): void {
    const state = this.$historyState();
    if (state === 'loading' || state === 'done') return;
    this.$historyState.set('loading');
    this.api.tracking.history(this.cursor ?? undefined).subscribe({
      next: ({ entries, has_more }) => {
        this.cursor = entries.at(-1) ?? this.cursor;
        // Entries checked here are already shown at the newest end.
        const shown = new Set(this.$history().map((entry) => entry.id));
        this.$history.update((history) => [...history, ...entries.filter((entry) => !shown.has(entry.id))]);
        this.$historyState.set(has_more ? 'idle' : 'done');
      },
      error: () => this.$historyState.set('failed'),
    });
  }

  /** Start the history over, as when the watch list opens afresh. */
  resetHistory(): void {
    this.$history.set([]);
    this.$historyState.set('idle');
    this.cursor = null;
  }

  /** Resume a show taken out by mistake: its card comes back where it was. */
  private undo(episode: Model.Http.WatchListEpisode, index: number): void {
    if (this.indexOf(episode.tmdb_id) === -1) this.restore(episode, index);
    this.writes++;
    void this.tracking.trackShow(episode.tmdb_id, 'watching').then((succeeded) => this.settled(succeeded, null, true));
  }

  private indexOf(tmdbId: number): number {
    return this.$episodes()?.findIndex((other) => other.tmdb_id === tmdbId) ?? -1;
  }

  /** Put a show's card back where it was, in place of the one shown for it now, if any. */
  private restore(card: Model.Http.WatchListEpisode, index: number): void {
    this.$checking.update((checking) => {
      const left = new Set(checking);
      left.delete(card.tmdb_id);
      return left;
    });
    this.$episodes.update((episodes) => {
      if (!episodes) return episodes;
      const rest = episodes.filter((other) => other.tmdb_id !== card.tmdb_id);
      const at = index === -1 ? rest.length : Math.min(index, rest.length);
      return [...rest.slice(0, at), card, ...rest.slice(at)];
    });
  }

  /** After a write: a failure, or a card the server must confirm, loads the list again once no write is left. */
  private settled(succeeded: boolean, entry: Model.Http.HistoryEntry | null, confirm: boolean): void {
    this.writes--;
    if (!succeeded && entry) this.$history.update((history) => history.filter((other) => other !== entry));
    if ((!succeeded || confirm) && this.writes === 0)
      this.load().subscribe({ error: () => this.$checking.set(new Set()) });
  }

  /** Put `next` in place of the show's card, or take the card out; a card watched again joins the top. */
  private replace(tmdbId: number, next: Model.Http.WatchListEpisode | null): void {
    this.$episodes.update((episodes) => {
      if (!episodes) return episodes;
      const index = episodes.findIndex((episode) => episode.tmdb_id === tmdbId);
      if (index === -1) return episodes;
      const rest = episodes.filter((_, other) => other !== index);
      if (!next) return rest;
      if (episodes[index].section === next.section)
        return episodes.map((episode, other) => (other === index ? next : episode));
      return [next, ...rest];
    });
  }

  /** A checked episode joins the history once the user has opened it, at its newest end. */
  private addToHistory(episode: Model.Http.WatchListEpisode, now: Date): Model.Http.HistoryEntry | null {
    if (this.$history().length === 0) return null;
    const entry = historyEntry(episode, now);
    this.$history.update((history) => [entry, ...history]);
    return entry;
  }
}

/** A watch list card's episode as the history lists it once watched. */
function historyEntry(episode: Model.Http.WatchListEpisode, watchedAt: Date): Model.Http.HistoryEntry {
  return {
    id: episode.episode_id,
    media_type: 'tv',
    tmdb_id: episode.tmdb_id,
    title: episode.show_title,
    poster_path: episode.poster_path,
    season_number: episode.season_number,
    episode_number: episode.episode_number,
    episode_title: episode.title,
    watched_at: watchedAt.toISOString(),
    // The server says whether the show is finished when the history loads again.
    finished: false,
  };
}
