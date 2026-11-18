import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, EMPTY, switchMap } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { injectTranslator } from '../../core/i18n';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { Poster } from '../../shared/poster';
import { injectStatusLabel } from '../../shared/status';

const STATUSES: Record<Model.Http.MediaType, Model.Http.TrackingStatus[]> = {
  tv: ['watching', 'up_to_date', 'watch_later', 'finished', 'stopped'],
  movie: ['watch_later', 'watched'],
};

/** The user's shows or movies, filtered by status. */
@Component({
  selector: 'app-library',
  imports: [RouterLink, Poster],
  templateUrl: './library.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Library {
  private readonly store = inject(TrackingStore);
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();
  protected readonly routes = appRoutes;
  protected readonly types: Model.Http.MediaType[] = ['tv', 'movie'];

  /** The `type` query parameter. */
  readonly type = input<Model.Http.MediaType, string | undefined>('tv', {
    transform: (value) => (value === 'movie' ? 'movie' : 'tv'),
  });
  protected readonly $status = signal<Model.Http.TrackingStatus | null>(null);

  protected readonly $statuses = computed(() => STATUSES[this.type()]);
  protected readonly $items = computed(() => this.store.library()[this.type()]);
  protected readonly $shown = computed(() => {
    const status = this.$status();
    return (this.$items() ?? []).filter((item) => status === null || item.status === status);
  });

  constructor() {
    // The cached list renders at once, so the scroll position comes back; the fresh one then replaces it.
    toObservable(this.type)
      .pipe(
        switchMap((type) => this.store.loadLibrary(type).pipe(catchError(() => EMPTY))),
        takeUntilDestroyed(),
      )
      .subscribe();
  }

  protected link(item: Model.Http.LibraryItem): string {
    return item.media_type === 'tv' ? appRoutes.show(item.tmdb_id) : appRoutes.movie(item.tmdb_id);
  }
}
