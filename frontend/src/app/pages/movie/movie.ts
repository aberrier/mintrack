import { ChangeDetectionStrategy, Component, computed, inject, input, numberAttribute, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { MatButton } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { catchError, EMPTY, filter, switchMap } from 'rxjs';
import { injectTranslator } from '../../core/i18n';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { ConfirmDialog, ConfirmDialogData } from '../../shared/confirm-dialog';
import { Poster } from '../../shared/poster';
import { injectStatusLabel } from '../../shared/status';

/** A movie: to watch later or watched. */
@Component({
  selector: 'app-movie',
  imports: [MatButton, Poster],
  templateUrl: './movie.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Movie {
  private readonly store = inject(TrackingStore);
  private readonly dialog = inject(MatDialog);
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();

  /** The `tmdbId` route parameter. */
  readonly tmdbId = input.required({ transform: numberAttribute });

  protected readonly $movie = computed(() => this.store.movies()[this.tmdbId()]);
  protected readonly $failed = signal(false);

  constructor() {
    toObservable(this.tmdbId)
      .pipe(
        switchMap((tmdbId) =>
          this.store.loadMovie(tmdbId).pipe(
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

  protected track(movie: Model.Http.Movie, watched: boolean): void {
    this.store.trackMovie(movie.tmdb_id, watched);
  }

  protected remove(movie: Model.Http.Movie): void {
    const data: ConfirmDialogData = {
      title: this.translate('app.movie.removeTitle'),
      message: this.translate('app.movie.removeMessage'),
      confirm: this.translate('app.common.remove'),
      cancel: this.translate('app.common.cancel'),
    };
    this.dialog
      .open<ConfirmDialog, ConfirmDialogData, boolean>(ConfirmDialog, { data })
      .afterClosed()
      .pipe(filter(Boolean))
      .subscribe(() => this.store.untrackMovie(movie.tmdb_id));
  }
}
