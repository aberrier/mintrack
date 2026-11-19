import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButton, MatIconButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../app.paths';
import { AuthStore } from '../../core/auth/auth.store';
import { injectTranslator, TranslationPath } from '../../core/i18n';
import { libraryKey, LibraryQuery, TrackingStore } from '../../core/tracking/tracking.store';
import { LoadError } from '../../shared/load-error';
import { MediaTile } from '../../shared/media-tile';
import { Skeleton } from '../../shared/skeleton';

const ROW_LENGTH = 20;

/**
 * The user's own place: their shows, movies and shows set aside to watch later, each row opening the whole
 * collection; a gear opens the settings.
 */
@Component({
  selector: 'app-profile',
  imports: [RouterLink, MatButton, MatIconButton, MatIcon, MediaTile, Skeleton, LoadError],
  templateUrl: './profile.html',
  styles: `
    .avatar {
      display: grid;
      flex: none;
      place-items: center;
      width: 56px;
      height: 56px;
      border-radius: var(--mat-sys-corner-full);
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
      font: var(--mat-sys-title-large);
      font-weight: 600;
      text-transform: uppercase;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Profile {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  private readonly tracking = inject(TrackingStore);

  protected readonly $user = inject(AuthStore).$user;
  protected readonly $initial = computed(() => this.$user()?.username.charAt(0) ?? '');

  /** The most recently watched first, as many as a row shows before See all. */
  protected readonly rowLength = ROW_LENGTH;
  protected readonly rows = [
    this.row('shows', { mediaType: 'tv' }, 'app.common.shows', 'app.profile.noShows'),
    this.row('movies', { mediaType: 'movie' }, 'app.common.movies', 'app.profile.noMovies'),
    // Shows set aside from the watch list, one tap away; the row hides while there is none.
    this.row('watch-later', { mediaType: 'tv', status: 'watch_later' }, 'app.status.watch_later', null),
  ];

  private row(id: string, query: LibraryQuery, title: TranslationPath<'app'>, empty: TranslationPath<'app'> | null) {
    const $failed = signal(false);
    const destroyRef = inject(DestroyRef);
    // The cached row renders at once; the fresh one then replaces it.
    const load = () => {
      $failed.set(false);
      this.tracking
        .loadLibrary(query)
        .pipe(takeUntilDestroyed(destroyRef))
        .subscribe({ error: () => $failed.set(true) });
    };
    load();
    const key = libraryKey(query);
    return {
      id,
      title: this.translate(title),
      empty: empty && this.translate(empty),
      seeAll: { type: query.mediaType, progress: query.status ?? null },
      $items: computed(() => this.tracking.library()[key]),
      $failed: $failed.asReadonly(),
      retry: load,
    };
  }
}
