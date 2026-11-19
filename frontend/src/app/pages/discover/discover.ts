import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { rxResource, toObservable, toSignal } from '@angular/core/rxjs-interop';
import { MatIcon } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { catchError, map, Observable, of, startWith, switchMap, timer } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { ApiService } from '../../core/api/api.service';
import { injectTranslator } from '../../core/i18n';
import { resultKey, TrackingStore } from '../../core/tracking/tracking.store';
import { EmptyState } from '../../shared/empty-state';
import { LoadError } from '../../shared/load-error';
import { MediaTile } from '../../shared/media-tile';
import { mediaTypeParam } from '../../shared/params';
import { Skeleton } from '../../shared/skeleton';
import { injectStatusLabel } from '../../shared/status';

type ResultsState =
  { kind: 'idle' | 'loading' | 'failed' | 'unconfigured' } | { kind: 'done'; results: Model.Http.SearchResult[] };

const DEBOUNCE_MS = 300;
const TYPES: Model.Http.MediaType[] = ['tv', 'movie'];

/**
 * Search among shows (anime included) or movies, the query and the type in the URL so back keeps them; without a
 * query, the week's trending shows and movies. The `+` on a poster adds the title to the library in one tap.
 */
@Component({
  selector: 'app-discover',
  imports: [RouterLink, MatIcon, MediaTile, EmptyState, Skeleton, LoadError],
  templateUrl: './discover.html',
  styles: `
    /* The search field: a full pill with the icon inside, the whole pill focusing the input. */
    .search {
      display: flex;
      align-items: center;
      gap: 12px;
      min-height: 56px;
      padding-inline: 16px;
      border-radius: var(--mat-sys-corner-full);
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
  protected readonly types = TYPES;

  /** The `q` query parameter. */
  readonly q = input<string, string | undefined>('', { transform: (value) => value ?? '' });
  /** The `type` query parameter: shows unless it says movie. */
  readonly type = input<Model.Http.MediaType, string | undefined>('tv', { transform: mediaTypeParam });
  /** Bumped by Try again, to send the same search again. */
  private readonly $attempt = signal(0);
  private readonly $search = computed(() => ({ query: this.q().trim(), type: this.type(), attempt: this.$attempt() }), {
    equal: (a, b) => a.query === b.query && a.type === b.type && a.attempt === b.attempt,
  });

  /** Earlier results go as soon as the query or the type changes; the search waits for typing to pause. */
  protected readonly $state = toSignal(
    toObservable(this.$search).pipe(
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

  protected readonly trending = TYPES.map((type) => ({
    id: type,
    title: this.translate(type === 'tv' ? 'app.discover.trendingShows' : 'app.discover.trendingMovies'),
    results: rxResource({ stream: () => this.api.catalog.trending(type) }),
  }));

  protected onInput(event: Event): void {
    const q = (event.target as HTMLInputElement).value;
    void this.router.navigate([], { queryParams: { q: q || null }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  protected retrySearch(): void {
    this.$attempt.update((attempt) => attempt + 1);
  }

  protected tracked(result: Model.Http.SearchResult): boolean {
    return result.tracking_status !== null || !!this.store.added()[resultKey(result.media_type, result.tmdb_id)];
  }

  /** The add was tapped and the server has not answered yet. */
  protected saving(result: Model.Http.SearchResult): boolean {
    return this.store.added()[resultKey(result.media_type, result.tmdb_id)] === 'saving';
  }

  protected detail(result: Model.Http.SearchResult): string | null {
    const status = result.tracking_status;
    return [result.year, status && this.statusLabel(status)].filter(Boolean).join(' · ') || null;
  }

  /** Add to the library at once: a show to start watching, a movie to watch later. */
  protected add(result: Model.Http.SearchResult): void {
    void this.store.addFromResults(result.media_type, result.tmdb_id);
  }

  /** Whether a trending request failed because the server has no TMDB key. */
  protected unconfigured(error: unknown): boolean {
    return isUnconfigured((error as { cause?: unknown } | undefined)?.cause ?? error);
  }
}

function isUnconfigured(error: unknown): boolean {
  return error instanceof HttpErrorResponse && error.status === 503;
}

function results(request: Observable<Model.Http.SearchResult[]>): Observable<ResultsState> {
  return request.pipe(
    map((results): ResultsState => ({ kind: 'done', results })),
    catchError((error: unknown) => of<ResultsState>({ kind: isUnconfigured(error) ? 'unconfigured' : 'failed' })),
  );
}
