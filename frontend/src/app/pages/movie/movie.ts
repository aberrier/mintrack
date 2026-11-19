import { ChangeDetectionStrategy, Component, computed, inject, input, numberAttribute } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { appRoutes } from '../../app.paths';
import { AuthStore } from '../../core/auth/auth.store';
import { formatDate } from '../../core/dates';
import { injectTranslator } from '../../core/i18n';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { BackButton } from '../../shared/back-button';
import { CheckButton } from '../../shared/check-button';
import { injectConfirm } from '../../shared/confirm-dialog';
import { LoadError } from '../../shared/load-error';
import { MediaHeader } from '../../shared/media-header';
import { loadMediaPage } from '../../shared/media-page';
import { RatingForm, tmdbScore } from '../../shared/rating-form';
import { Skeleton } from '../../shared/skeleton';
import { injectStatusLabel } from '../../shared/status';

/** A movie: its header, when it was watched, and one check to mark or unmark it. */
@Component({
  selector: 'app-movie',
  imports: [MatButton, CheckButton, MediaHeader, Skeleton, LoadError, BackButton, RatingForm],
  templateUrl: './movie.html',
  styles: `
    /* Whether the movie is watched, on a tinted card with its check. */
    .watched {
      display: flex;
      align-items: center;
      gap: 16px;
      min-height: 64px;
      padding: 8px 4px 8px 16px;
      border-radius: var(--mat-sys-corner-large);
      background: var(--mat-sys-surface-container-low);
    }
    .status {
      padding: 4px 12px;
      border-radius: var(--mat-sys-corner-small);
      background: var(--mat-sys-secondary-container);
      color: var(--mat-sys-on-secondary-container);
      font: var(--mat-sys-label-large);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Movie {
  protected readonly store = inject(TrackingStore);
  private readonly confirm = injectConfirm();
  private readonly timeZone = inject(AuthStore).$timeZone;
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();
  /** Back from a movie opened first: the Profile tab's movies. */
  protected readonly fallback = `${appRoutes.collection()}?type=movie`;

  /** The `tmdbId` route parameter. */
  readonly tmdbId = input.required({ transform: numberAttribute });

  protected readonly $movie = computed(() => this.store.movies()[this.tmdbId()]);
  protected readonly page = loadMediaPage(this.tmdbId, (tmdbId) => this.store.loadMovie(tmdbId), this.$movie);

  protected readonly $facts = computed(() => {
    const movie = this.$movie();
    if (!movie) return [];
    return [
      movie.runtime ? this.runtime(movie.runtime) : null,
      movie.release_date && formatDate(movie.release_date, this.timeZone()),
    ].filter((fact): fact is string => !!fact);
  });

  protected readonly $tmdbScore = computed(() => tmdbScore(this.translate, this.$movie()));

  protected readonly $watchedOn = computed(() => {
    const watchedAt = this.$movie()?.tracking?.watched_at;
    return watchedAt ? formatDate(watchedAt, this.timeZone()) : null;
  });

  /** The check: watched now, or back to watch later. */
  protected toggle(movie: Model.Http.Movie): void {
    void this.store.trackMovie(movie.tmdb_id, movie.tracking?.status !== 'watched');
  }

  protected watchLater(movie: Model.Http.Movie): void {
    void this.store.trackMovie(movie.tmdb_id, false);
  }

  protected remove(movie: Model.Http.Movie): void {
    this.confirm({
      title: this.translate('app.movie.removeTitle'),
      message: this.translate('app.movie.removeMessage'),
      confirm: this.translate('app.common.remove'),
    }).subscribe(() => void this.store.untrackMovie(movie.tmdb_id));
  }

  private runtime(minutes: number): string {
    const hours = Math.floor(minutes / 60);
    return hours
      ? this.translate('app.movie.runtime', { hours: String(hours), minutes: String(minutes % 60) })
      : this.translate('app.movie.runtimeMinutes', { minutes: String(minutes) });
  }
}
