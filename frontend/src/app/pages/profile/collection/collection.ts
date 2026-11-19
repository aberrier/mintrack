import { ChangeDetectionStrategy, Component, computed, inject, input, OnInit, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { MatFormField, MatLabel, MatPrefix } from '@angular/material/form-field';
import { MatIcon } from '@angular/material/icon';
import { MatInput } from '@angular/material/input';
import { Router } from '@angular/router';
import { appRoutes } from '../../../app.paths';
import { injectTranslator } from '../../../core/i18n';
import { libraryKey, LibraryQuery, TrackingStore } from '../../../core/tracking/tracking.store';
import { BackButton } from '../../../shared/back-button';
import { EmptyState } from '../../../shared/empty-state';
import { LoadError } from '../../../shared/load-error';
import { MediaTile } from '../../../shared/media-tile';
import { mediaTypeParam } from '../../../shared/params';
import { Skeleton } from '../../../shared/skeleton';
import { injectStatusLabel } from '../../../shared/status';

const SORTS: Model.Http.LibrarySort[] = ['last_watched', 'last_added', 'title'];
const PROGRESS: Record<Model.Http.MediaType, Model.Http.TrackingStatus[]> = {
  tv: ['watching', 'not_started', 'watch_later', 'up_to_date', 'finished', 'stopped'],
  movie: ['watch_later', 'watched'],
};
const ALL_PROGRESS: Model.Http.TrackingStatus[] = Object.values(PROGRESS).flat();

/**
 * All the user's shows or movies as a grid, searched by title, sorted and filtered by progress; the three choices live
 * in the URL.
 */
@Component({
  selector: 'app-collection',
  imports: [
    MediaTile,
    EmptyState,
    Skeleton,
    LoadError,
    BackButton,
    MatFormField,
    MatLabel,
    MatPrefix,
    MatInput,
    MatIcon,
  ],
  templateUrl: './collection.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Collection implements OnInit {
  private readonly store = inject(TrackingStore);
  private readonly router = inject(Router);
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();
  protected readonly sorts = SORTS;
  protected readonly routes = appRoutes;

  /** The `type` query parameter. */
  readonly type = input<Model.Http.MediaType, string | undefined>('tv', { transform: mediaTypeParam });
  /** The `sort` query parameter: last watched first unless it names another order. */
  readonly sort = input<Model.Http.LibrarySort, string | undefined>('last_watched', {
    transform: (value) => SORTS.find((sort) => sort === value) ?? 'last_watched',
  });
  /** The `progress` query parameter: a library status, or all. */
  readonly progress = input<Model.Http.TrackingStatus | null, string | undefined>(null, {
    transform: (value) => ALL_PROGRESS.find((status) => status === value) ?? null,
  });

  /** The `q` query parameter: text the titles must contain. */
  readonly q = input<string, string | undefined>('', { transform: (value) => value ?? '' });
  /**
   * The search field's text, read from the address once: typing then leads and the address follows, so a navigation
   * still on its way never puts back an older text.
   */
  protected readonly $search = signal('');

  protected readonly $progressOptions = computed(() => PROGRESS[this.type()]);
  private readonly $query = computed(
    (): LibraryQuery => ({
      mediaType: this.type(),
      sort: this.sort(),
      status: this.$progressOptions().find((status) => status === this.progress()) ?? null,
    }),
    { equal: (a, b) => libraryKey(a) === libraryKey(b) },
  );
  protected readonly $status = computed(() => this.$query().status ?? null);
  /** The cached grid renders at once, so the scroll position comes back; the fresh one then replaces it. */
  protected readonly $items = computed(() => this.store.library()[libraryKey(this.$query())]);
  protected readonly $shownItems = computed(() => {
    const search = this.$search().trim().toLowerCase();
    const items = this.$items();
    return search && items ? items.filter((item) => item.title.toLowerCase().includes(search)) : items;
  });
  protected readonly library = rxResource({
    params: () => this.$query(),
    stream: ({ params }) => this.store.loadLibrary(params),
  });

  ngOnInit(): void {
    this.$search.set(this.q());
  }

  protected choose(params: { sort?: Model.Http.LibrarySort; progress?: Model.Http.TrackingStatus | null }): void {
    const queryParams: Record<string, string | null> = {};
    if (params.sort) queryParams['sort'] = params.sort === 'last_watched' ? null : params.sort;
    if (params.progress !== undefined) queryParams['progress'] = params.progress;
    void this.router.navigate([], { queryParams, queryParamsHandling: 'merge', replaceUrl: true });
  }

  protected search(text: string): void {
    this.$search.set(text);
    void this.router.navigate([], { queryParams: { q: text || null }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  protected sortLabel(sort: Model.Http.LibrarySort): string {
    return this.translate(`app.collection.sort.${sort}`);
  }

  protected detail(item: Model.Http.LibraryItem): string {
    const status = this.statusLabel(item.status);
    return item.media_type === 'tv' ? `${item.watched_count}/${item.aired_count} · ${status}` : status;
  }
}
