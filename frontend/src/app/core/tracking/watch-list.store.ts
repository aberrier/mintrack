import { inject, Injectable, signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable, of, tap } from 'rxjs';
import { ApiService } from '../api/api.service';
import { injectTranslator } from '../i18n';
import { followingEpisode } from './episodes';
import { TrackingStore } from './tracking.store';

export type HistoryState = 'idle' | 'loading' | 'failed' | 'done';

/**
 * The watch list (the next episode of each show in progress) and the watch history above it.
 *
 * A check is optimistic: the card moves to the following episode, computed from the show (loaded once), or leaves the
 * list, before the server answers; the write goes through `TrackingStore`, which says when it fails, and the list is
 * then loaded again from the server.
 */
@Injectable({ providedIn: 'root' })
export class WatchListStore {
  private readonly api = inject(ApiService);
  private readonly tracking = inject(TrackingStore);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = injectTranslator('app');

  private readonly $episodes = signal<Model.Http.WatchListEpisode[] | undefined>(undefined);
  private readonly $history = signal<Model.Http.HistoryEntry[]>([]);
  private readonly $historyState = signal<HistoryState>('idle');
  private readonly $checking = signal<ReadonlySet<string>>(new Set());
  /** The oldest entry the server sent, from which the next page starts. */
  private cursor: Model.Http.HistoryEntry | null = null;
  private writes = 0;

  /** The last list loaded, with the taps since; most recently watched first. */
  readonly episodes = this.$episodes.asReadonly();
  /** Watched episodes and movies, newest first. */
  readonly history = this.$history.asReadonly();
  readonly historyState = this.$historyState.asReadonly();
  /** Episodes checked whose card waits for its show to move on. */
  readonly checking = this.$checking.asReadonly();

  load(): Observable<Model.Http.WatchListResponse> {
    return this.api.upcoming.watchList().pipe(
      tap((response) => {
        // A list loaded while taps are on their way would undo them on screen.
        if (this.writes === 0) this.$episodes.set(response.episodes);
      }),
    );
  }

  /** Mark the card's episode watched now and move the card on. */
  check(episode: Model.Http.WatchListEpisode, now = new Date()): void {
    if (this.$checking().has(episode.episode_id)) return;
    const tmdbId = episode.tmdb_id;
    const loaded = this.tracking.shows()[tmdbId];
    if (!loaded && episode.remaining === 0) this.replace(tmdbId, null);
    else if (!loaded) this.$checking.update((ids) => new Set(ids).add(episode.episode_id));
    this.writes++;

    (loaded ? of(loaded) : this.tracking.loadShow(tmdbId)).subscribe({
      next: () => {
        this.unchecking(episode.episode_id);
        const written = this.tracking.setWatched(tmdbId, [episode.episode_id], true);
        const show = this.tracking.shows()[tmdbId];
        const following = followingEpisode(show, episode.season_number, episode.episode_number, now);
        this.replace(
          tmdbId,
          following && {
            ...episode,
            episode_id: following.episode.id,
            season_number: following.episode.season_number,
            episode_number: following.episode.episode_number,
            title: following.episode.title,
            airstamp: following.episode.airstamp,
            day: following.episode.air_date,
            remaining: following.remaining,
            last_watched_at: now.toISOString(),
            section: 'next',
          },
        );
        const entry = this.addToHistory(episode, now);
        void written.then((succeeded) => this.settled(succeeded, entry));
      },
      error: () => {
        this.unchecking(episode.episode_id);
        this.writes--;
        this.reload();
        this.snackBar.open(this.translate('app.tracking.saveFailed'), undefined, { duration: 4000 });
      },
    });
  }

  /** Take the show out of the watch list: to watch later, or stopped. */
  remove(episode: Model.Http.WatchListEpisode, status: 'watch_later' | 'stopped'): void {
    this.replace(episode.tmdb_id, null);
    this.writes++;
    void this.tracking.trackShow(episode.tmdb_id, status).then((succeeded) => this.settled(succeeded, null));
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

  private settled(succeeded: boolean, entry: Model.Http.HistoryEntry | null): void {
    this.writes--;
    if (succeeded) return;
    if (entry) this.$history.update((history) => history.filter((other) => other !== entry));
    this.reload();
  }

  private reload(): void {
    if (this.writes === 0) this.load().subscribe({ error: () => undefined });
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
    const entry: Model.Http.HistoryEntry = {
      id: episode.episode_id,
      media_type: 'tv',
      tmdb_id: episode.tmdb_id,
      title: episode.show_title,
      poster_path: episode.poster_path,
      season_number: episode.season_number,
      episode_number: episode.episode_number,
      episode_title: episode.title,
      watched_at: now.toISOString(),
    };
    this.$history.update((history) => [entry, ...history]);
    return entry;
  }

  private unchecking(episodeId: string): void {
    if (!this.$checking().has(episodeId)) return;
    this.$checking.update((ids) => {
      const next = new Set(ids);
      next.delete(episodeId);
      return next;
    });
  }
}
