import { ChangeDetectionStrategy, Component, computed, inject, input, numberAttribute, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { MatButton } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import { catchError, EMPTY, filter, switchMap } from 'rxjs';
import { injectTranslator } from '../../core/i18n';
import {
  isComplete,
  isWatched,
  nextToWatch,
  previousUnwatched,
  seasonProgress,
  SPECIALS,
} from '../../core/tracking/episodes';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { Confetti } from '../../shared/confetti';
import { ConfirmDialog, ConfirmDialogData } from '../../shared/confirm-dialog';
import { CardEpisode, EpisodeCard } from '../../shared/episode-card/episode-card';
import { MediaHeader } from '../../shared/media-header';
import { Skeleton } from '../../shared/skeleton';
import { injectStatusLabel } from '../../shared/status';
import { SeasonRow } from './season-row';

const PREVIOUS_OFFER_MS = 6000;

type ShowTab = 'episodes' | 'about';

/**
 * A show: its header, then About (the overview and facts) or Episodes, where the next episode, each season and each
 * episode are marked in one tap. Finishing an ended show throws confetti.
 */
@Component({
  selector: 'app-show',
  imports: [RouterLink, MatButton, EpisodeCard, MediaHeader, SeasonRow, Skeleton],
  templateUrl: './show.html',
  styleUrl: './show.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Show {
  private readonly store = inject(TrackingStore);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  private readonly confetti = inject(Confetti);
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();
  protected readonly tabs: ShowTab[] = ['about', 'episodes'];

  /** The `tmdbId` route parameter. */
  readonly tmdbId = input.required({ transform: numberAttribute });
  /** The `tab` query parameter: episodes unless it says about. */
  readonly tab = input<ShowTab, string | undefined>('episodes', {
    transform: (value) => (value === 'about' ? 'about' : 'episodes'),
  });

  protected readonly $show = computed(() => this.store.shows()[this.tmdbId()]);
  protected readonly $failed = signal(false);
  /** Seasons open to their episodes, by number. */
  protected readonly $expanded = signal<ReadonlySet<number>>(new Set());
  /** Air dates are compared with the time the page opened. */
  protected readonly now = new Date();

  protected readonly $facts = computed(() => {
    const show = this.$show();
    if (!show) return [];
    const seasons = show.seasons.filter((season) => season.season_number !== SPECIALS).length;
    return [
      this.translate(seasons === 1 ? 'app.show.seasonsOne' : 'app.show.seasons', { count: String(seasons) }),
      show.network,
    ].filter((fact): fact is string => !!fact);
  });

  protected readonly $next = computed((): CardEpisode | null => {
    const show = this.$show();
    const next = show && nextToWatch(show, this.now);
    if (!next) return null;
    return {
      tmdb_id: show.tmdb_id,
      show_title: show.title,
      poster_path: show.poster_path,
      season_number: next.episode.season_number,
      episode_number: next.episode.episode_number,
      title: next.episode.title,
      remaining: next.remaining,
    };
  });

  constructor() {
    toObservable(this.tmdbId)
      .pipe(
        switchMap((tmdbId) =>
          this.store.loadShow(tmdbId).pipe(
            catchError(() => {
              this.$failed.set(true);
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe();
  }

  protected toggleSeason(season: Model.Http.Season): void {
    this.$expanded.update((open) => {
      const next = new Set(open);
      if (!next.delete(season.season_number)) next.add(season.season_number);
      return next;
    });
  }

  /** The Watch next card's check. */
  protected markNext(show: Model.Http.Show): void {
    const next = nextToWatch(show, this.now);
    if (next) this.mark(show, [next.episode], true);
  }

  /** An episode's check: marks it, offering the earlier unwatched ones, or unmarks it. */
  protected tapEpisode(show: Model.Http.Show, episode: Model.Http.Episode): void {
    if (isWatched(show, episode)) {
      this.mark(show, [episode], false);
      return;
    }
    const previous = previousUnwatched(show, episode, this.now);
    this.mark(show, [episode], true);
    if (previous.length === 0) return;
    this.snackBar
      .open(
        this.translate(previous.length === 1 ? 'app.show.previousOne' : 'app.show.previousMany', {
          count: String(previous.length),
        }),
        this.translate('app.show.markPrevious'),
        { duration: PREVIOUS_OFFER_MS },
      )
      .onAction()
      .subscribe(() => this.mark(this.$show(), previous, true));
  }

  /** A season's check: marks its aired episodes, or, once they all are, unmarks the season after asking. */
  protected checkSeason(show: Model.Http.Show, season: Model.Http.Season): void {
    const progress = seasonProgress(show, season, this.now);
    if (!progress.complete) {
      this.mark(show, progress.toMark, true);
      return;
    }
    const data: ConfirmDialogData = {
      title: this.translate('app.show.unmarkTitle', { season: season.title }),
      message: this.translate('app.show.unmarkMessage'),
      confirm: this.translate('app.show.unmark'),
      cancel: this.translate('app.common.cancel'),
    };
    this.dialog
      .open<ConfirmDialog, ConfirmDialogData, boolean>(ConfirmDialog, { data })
      .afterClosed()
      .pipe(filter(Boolean))
      .subscribe(() => {
        const current = this.$show();
        this.mark(
          current,
          season.episodes.filter((episode) => isWatched(current, episode)),
          false,
        );
      });
  }

  protected track(show: Model.Http.Show, status: Model.Http.ShowTrackingChoice): void {
    void this.store.trackShow(show.tmdb_id, status);
  }

  protected remove(show: Model.Http.Show): void {
    const data: ConfirmDialogData = {
      title: this.translate('app.show.removeTitle'),
      message: this.translate('app.show.removeMessage'),
      confirm: this.translate('app.common.remove'),
      cancel: this.translate('app.common.cancel'),
    };
    this.dialog
      .open<ConfirmDialog, ConfirmDialogData, boolean>(ConfirmDialog, { data })
      .afterClosed()
      .pipe(filter(Boolean))
      .subscribe(() => void this.store.untrackShow(show.tmdb_id));
  }

  /** Mark or unmark episodes. The store shows them at once, so finishing the show is celebrated at once too. */
  private mark(show: Model.Http.Show, episodes: Model.Http.Episode[], watched: boolean): void {
    if (episodes.length === 0) return;
    const wasComplete = isComplete(show, this.now);
    void this.store.setWatched(
      show.tmdb_id,
      episodes.map((episode) => episode.id),
      watched,
    );
    const updated = this.store.shows()[show.tmdb_id];
    if (watched && !wasComplete && updated && isComplete(updated, this.now)) this.confetti.launch();
  }
}
