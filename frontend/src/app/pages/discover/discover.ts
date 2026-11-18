import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { MatIcon } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { catchError, distinctUntilChanged, map, Observable, of, startWith, switchMap, timer } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { ApiService } from '../../core/api/api.service';
import { injectTranslator } from '../../core/i18n';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { EmptyState } from '../../shared/empty-state';
import { MediaTile } from '../../shared/media-tile';
import { Skeleton } from '../../shared/skeleton';
import { injectStatusLabel } from '../../shared/status';

type ResultsState =
  { kind: 'idle' | 'loading' | 'failed' | 'unconfigured' } | { kind: 'done'; results: Model.Http.SearchResult[] };

const DEBOUNCE_MS = 300;

/**
 * Search among shows (anime included) or movies, the query and the type in the URL so back keeps them; without a
 * query, the week's trending shows and movies. The `+` on a poster adds the title to the library in one tap.
 */
@Component({
  selector: 'app-discover',
  imports: [NgTemplateOutlet, RouterLink, MatIcon, MediaTile, EmptyState, Skeleton],
  templateUrl: './discover.html',
  styles: `
    /* The search field: a full pill with the icon inside, the whole pill focusing the input. */
    .search {
      display: flex;
      align-items: center;
      gap: 12px;
      min-height: 56px;
      padding-inline: 16px;
      border-radius: 28px;
      background: var(--mat-sys-surface-container-high);
      color: var(--mat-sys-on-surface-variant);
      cursor: text;
      transition: box-shadow var(--duration-toggle) var(--ease-standard);
    }
    .search:focus-within {
      box-shadow: inset 0 0 0 2px var(--mat-sys-primary);
    }
    input {
      flex: 1;
      min-width: 0;
      min-height: 48px;
      border: 0;
      background: none;
      color: var(--mat-sys-on-surface);
      font: var(--mat-sys-body-large);
      outline: none;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Discover {
  private readonly api = inject(ApiService);
  private readonly store = inject(TrackingStore);
  private readonly router = inject(Router);
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();
  protected readonly routes = appRoutes;
  protected readonly types: Model.Http.MediaType[] = ['tv', 'movie'];

  /** The `q` query parameter. */
  readonly q = input<string, string | undefined>('', { transform: (value) => value ?? '' });
  /** The `type` query parameter: shows unless it says movie. */
  readonly type = input<Model.Http.MediaType, string | undefined>('tv', {
    transform: (value) => (value === 'movie' ? 'movie' : 'tv'),
  });
  private readonly $search = computed(() => ({ query: this.q().trim(), type: this.type() }));

  /** Titles added from this page, by `type:id`, ahead of the server's statuses. */
  private readonly $added = signal<Record<string, boolean>>({});

  /** Earlier results go as soon as the query or the type changes; the search waits for typing to pause. */
  protected readonly $state = toSignal(
    toObservable(this.$search).pipe(
      distinctUntilChanged((a, b) => a.query === b.query && a.type === b.type),
      switchMap(({ query, type }) =>
        query
          ? timer(DEBOUNCE_MS).pipe(
              switchMap(() => results(this.api.catalog.search(query, type))),
              startWith<ResultsState>({ kind: 'loading' }),
            )
          : of<ResultsState>({ kind: 'idle' }),
      ),
    ),
    { initialValue: { kind: 'idle' } as ResultsState },
  );

  protected readonly trending = [
    {
      id: 'tv',
      title: this.translate('app.discover.trendingShows'),
      $state: toSignal(results(this.api.catalog.trending('tv')), { requireSync: true }),
    },
    {
      id: 'movie',
      title: this.translate('app.discover.trendingMovies'),
      $state: toSignal(results(this.api.catalog.trending('movie')), { requireSync: true }),
    },
  ];

  protected onInput(event: Event): void {
    const q = (event.target as HTMLInputElement).value;
    void this.router.navigate([], { queryParams: { q: q || null }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  protected link(result: Model.Http.SearchResult): string {
    return result.media_type === 'tv' ? appRoutes.show(result.tmdb_id) : appRoutes.movie(result.tmdb_id);
  }

  protected tracked(result: Model.Http.SearchResult): boolean {
    return result.tracking_status !== null || !!this.$added()[key(result)];
  }

  protected detail(result: Model.Http.SearchResult): string | null {
    const status = result.tracking_status;
    return [result.year, status && this.statusLabel(status)].filter(Boolean).join(' · ') || null;
  }

  /** Add to the library at once: a show to start watching, a movie to watch later. */
  protected async add(result: Model.Http.SearchResult): Promise<void> {
    const id = key(result);
    this.$added.update((added) => ({ ...added, [id]: true }));
    const saved = await this.store.addFromResults(result.media_type, result.tmdb_id);
    if (!saved) this.$added.update((added) => ({ ...added, [id]: false }));
  }
}

function key(result: Model.Http.SearchResult): string {
  return `${result.media_type}:${result.tmdb_id}`;
}

function results(request: Observable<Model.Http.SearchResult[]>): Observable<ResultsState> {
  return request.pipe(
    map((results): ResultsState => ({ kind: 'done', results })),
    catchError((error: unknown) =>
      of<ResultsState>({
        kind: error instanceof HttpErrorResponse && error.status === 503 ? 'unconfigured' : 'failed',
      }),
    ),
    startWith<ResultsState>({ kind: 'loading' }),
  );
}
