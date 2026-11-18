import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { catchError, debounceTime, distinctUntilChanged, map, of, startWith, switchMap } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { ApiService } from '../../core/api/api.service';
import { injectTranslator } from '../../core/i18n';
import { Poster } from '../../shared/poster';
import { injectStatusLabel } from '../../shared/status';

type SearchState =
  { kind: 'idle' | 'loading' | 'failed' | 'unconfigured' } | { kind: 'done'; results: Model.Http.SearchResult[] };

const DEBOUNCE_MS = 300;

/** TMDB search for shows (anime included) and movies; the query lives in the URL, so back keeps it. */
@Component({
  selector: 'app-search',
  imports: [RouterLink, Poster],
  templateUrl: './search.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Search {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();

  /** The `q` query parameter. */
  readonly q = input<string, string | undefined>('', { transform: (value) => value ?? '' });

  protected readonly $state = toSignal(
    toObservable(this.q).pipe(
      map((query) => query.trim()),
      debounceTime(DEBOUNCE_MS),
      distinctUntilChanged(),
      switchMap((query) =>
        query
          ? this.api.catalog.search(query).pipe(
              map((results): SearchState => ({ kind: 'done', results })),
              catchError((error: unknown) =>
                of<SearchState>({
                  kind: error instanceof HttpErrorResponse && error.status === 503 ? 'unconfigured' : 'failed',
                }),
              ),
              startWith<SearchState>({ kind: 'loading' }),
            )
          : of<SearchState>({ kind: 'idle' }),
      ),
    ),
    { initialValue: { kind: 'idle' } as SearchState },
  );

  protected onInput(event: Event): void {
    const q = (event.target as HTMLInputElement).value;
    void this.router.navigate([], { queryParams: { q: q || null }, replaceUrl: true });
  }

  protected link(result: Model.Http.SearchResult): string {
    return result.media_type === 'tv' ? appRoutes.show(result.tmdb_id) : appRoutes.movie(result.tmdb_id);
  }
}
