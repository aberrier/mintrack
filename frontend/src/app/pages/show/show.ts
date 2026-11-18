import { ChangeDetectionStrategy, Component, computed, inject, input, numberAttribute, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { MatButton, MatIconButton } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIcon } from '@angular/material/icon';
import { MatMenu, MatMenuItem, MatMenuTrigger } from '@angular/material/menu';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, EMPTY, filter, switchMap } from 'rxjs';
import { injectTranslator } from '../../core/i18n';
import { isUpcoming, isWatched, previousUnwatched, SPECIALS } from '../../core/tracking/episodes';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { ConfirmDialog, ConfirmDialogData } from '../../shared/confirm-dialog';
import { Poster } from '../../shared/poster';
import { injectStatusLabel } from '../../shared/status';

const PREVIOUS_OFFER_MS = 6000;

/** A show: its seasons and episodes, one tap to mark or unmark an episode. */
@Component({
  selector: 'app-show',
  imports: [MatButton, MatIconButton, MatIcon, MatMenu, MatMenuItem, MatMenuTrigger, Poster],
  templateUrl: './show.html',
  styleUrl: './show.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Show {
  private readonly store = inject(TrackingStore);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();
  protected readonly specials = SPECIALS;

  /** The `tmdbId` route parameter. */
  readonly tmdbId = input.required({ transform: numberAttribute });

  protected readonly $show = computed(() => this.store.shows()[this.tmdbId()]);
  protected readonly $failed = signal(false);
  /** Air dates are compared with the time the page opened. */
  protected readonly now = new Date();

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

  protected upcoming(episode: Model.Http.Episode): boolean {
    return isUpcoming(episode, this.now);
  }

  protected watched(show: Model.Http.Show, episode: Model.Http.Episode): boolean {
    return isWatched(show, episode);
  }

  protected watchedCount(show: Model.Http.Show, season: Model.Http.Season): number {
    return season.episodes.filter((episode) => isWatched(show, episode)).length;
  }

  protected toggle(show: Model.Http.Show, episode: Model.Http.Episode): void {
    if (isWatched(show, episode)) {
      this.store.setWatched(show.tmdb_id, [episode.id], false);
      return;
    }
    const previous = previousUnwatched(show, episode, this.now);
    this.store.setWatched(show.tmdb_id, [episode.id], true);
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
      .subscribe(() =>
        this.store.setWatched(
          show.tmdb_id,
          previous.map((e) => e.id),
          true,
        ),
      );
  }

  protected markSeason(show: Model.Http.Show, season: Model.Http.Season, watched: boolean): void {
    const episodes = season.episodes.filter((episode) =>
      watched ? !this.upcoming(episode) && !isWatched(show, episode) : isWatched(show, episode),
    );
    if (episodes.length > 0)
      this.store.setWatched(
        show.tmdb_id,
        episodes.map((e) => e.id),
        watched,
      );
  }

  protected track(show: Model.Http.Show, stopped: boolean): void {
    this.store.trackShow(show.tmdb_id, stopped);
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
      .subscribe(() => this.store.untrackShow(show.tmdb_id));
  }
}
