import { ChangeDetectionStrategy, Component, computed, inject, input, numberAttribute, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { MatButton } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { catchError, EMPTY, filter, switchMap } from 'rxjs';
import { injectTranslator } from '../../core/i18n';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { CheckMark } from '../../shared/check-mark';
import { ConfirmDialog, ConfirmDialogData } from '../../shared/confirm-dialog';
import { MediaHeader } from '../../shared/media-header';
import { Skeleton } from '../../shared/skeleton';
import { injectStatusLabel } from '../../shared/status';

/** A movie: its header, when it was watched, and one check to mark or unmark it. */
@Component({
  selector: 'app-movie',
  imports: [MatButton, CheckMark, MediaHeader, Skeleton],
  templateUrl: './movie.html',
  styles: `
    /* Whether the movie is watched, on a tinted card with its check. */
    .watched {
      display: flex;
      align-items: center;
      gap: 16px;
      min-height: 64px;
      padding: 8px 4px 8px 16px;
      border-radius: 16px;
      background: var(--mat-sys-surface-container-low);
    }
    .status {
      padding: 4px 12px;
      border-radius: 8px;
      background: var(--mat-sys-secondary-container);
      color: var(--mat-sys-on-secondary-container);
      font: var(--mat-sys-label-large);
    }
    /* A 48px target around the 36px mark. */
    .check {
      display: grid;
      flex: none;
      place-items: center;
      width: 48px;
      height: 48px;
      padding: 0;
      border: 0;
      background: none;
      cursor: pointer;
    }
    app-check-mark {
      transition: transform var(--duration-short) var(--ease-standard);
    }
    .check:active app-check-mark {
      transform: scale(0.9);
    }
    .check:focus-visible {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -2px;
    }
  `,
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

  protected readonly $facts = computed(() => {
    const movie = this.$movie();
    if (!movie) return [];
    return [
      movie.runtime ? this.runtime(movie.runtime) : null,
      movie.release_date && formatDate(movie.release_date),
    ].filter((fact): fact is string => !!fact);
  });

  protected readonly $watchedOn = computed(() => {
    const watchedAt = this.$movie()?.tracking?.watched_at;
    return watchedAt ? formatDate(watchedAt) : null;
  });

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

  /** The check: watched now, or back to watch later. */
  protected toggle(movie: Model.Http.Movie): void {
    void this.store.trackMovie(movie.tmdb_id, movie.tracking?.status !== 'watched');
  }

  protected watchLater(movie: Model.Http.Movie): void {
    void this.store.trackMovie(movie.tmdb_id, false);
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
      .subscribe(() => void this.store.untrackMovie(movie.tmdb_id));
  }

  private runtime(minutes: number): string {
    const hours = Math.floor(minutes / 60);
    return hours
      ? this.translate('app.movie.runtime', { hours: String(hours), minutes: String(minutes % 60) })
      : this.translate('app.movie.runtimeMinutes', { minutes: String(minutes) });
  }
}

/** A date such as 1 May 2020, from an ISO date or date-time. */
function formatDate(iso: string): string {
  const dateOnly = iso.length === 10;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeZone: dateOnly ? 'UTC' : undefined,
  }).format(new Date(iso));
}
