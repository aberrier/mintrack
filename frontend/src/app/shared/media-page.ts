import { HttpErrorResponse } from '@angular/common/http';
import { computed, effect, inject, Signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';
import { TranslationPath } from '../core/i18n';
import { AppTitleStrategy } from '../core/title';

/**
 * Load a show's or a movie's page into its store (the page reads it from there, with the user's taps), name the
 * browser tab after it, and say why it failed: unknown to TMDB, or anything else, with a way to try again.
 */
export function loadMediaPage<T extends { title: string }>(
  tmdbId: Signal<number>,
  load: (tmdbId: number) => Observable<T>,
  loaded: Signal<T | undefined>,
): { $error: Signal<TranslationPath<'app'> | null>; retry: () => void } {
  const resource = rxResource({ params: () => tmdbId(), stream: ({ params }) => load(params) });
  const titles = inject(AppTitleStrategy);
  effect(() => {
    const media = loaded();
    if (media) titles.setPage(media.title);
  });
  const $error = computed((): TranslationPath<'app'> | null => {
    const error = resource.error();
    if (!error || loaded()) return null;
    const cause = (error as { cause?: unknown }).cause ?? error;
    return cause instanceof HttpErrorResponse && cause.status === 404 ? 'app.common.notFound' : 'app.common.loadFailed';
  });
  return { $error, retry: () => resource.reload() };
}
