import { DestroyRef, DOCUMENT, inject, Injector } from '@angular/core';
import { NavigationError } from '@angular/router';
import { SwUpdate } from '@angular/service-worker';
import { filter, map, merge } from 'rxjs';
import { PAGE_LOCATION } from '../auth/auth.store';
import { injectTranslator, TranslationPath } from '../i18n';

const RELOADED_KEY = 'mintrack.reloadedFor';

/**
 * Offers a reload when a new version is ready, or when the cached one can no longer run. An app left open in the
 * background looks for a new version each time it comes back to the screen.
 */
export function promptForUpdates(): void {
  const updates = inject(SwUpdate);
  if (!updates.isEnabled) return;
  const injector = inject(Injector);
  const document = inject(DOCUMENT);
  const translate = injectTranslator('app');

  const listening = new AbortController();
  document.addEventListener(
    'visibilitychange',
    () => document.visibilityState === 'visible' && updates.checkForUpdate().catch(() => undefined),
    { signal: listening.signal },
  );
  inject(DestroyRef).onDestroy(() => listening.abort());

  merge(
    updates.versionUpdates.pipe(
      filter((event) => event.type === 'VERSION_READY'),
      map((): TranslationPath<'app'> => 'app.update.ready'),
    ),
    updates.unrecoverable.pipe(map((): TranslationPath<'app'> => 'app.update.broken')),
  ).subscribe(async (message) => {
    // Loaded on first use: the snackbar stays out of the initial bundle.
    const { MatSnackBar } = await import('@angular/material/snack-bar');
    const snackBar = injector.get(MatSnackBar);
    // Another message replaces the prompt for a while: it comes back once that one is gone.
    const prompt = () => {
      const ref = snackBar.open(translate(message), translate('app.update.reload'));
      ref.onAction().subscribe(() => document.location.reload());
      ref.afterDismissed().subscribe(({ dismissedByAction }) => {
        if (!dismissedByAction) snackBar._openedSnackBarRef?.afterDismissed().subscribe(prompt);
      });
    };
    prompt();
  });
}

/**
 * A page's code that is gone from the server (a tab opened before a new version was deployed) loads the app again at
 * that page, once: a second failure for the same address is left to the router. Offline, the code is only out of
 * reach and a reload would fail too.
 */
export function reloadOnMissingChunk(error: NavigationError): void {
  const message = error.error instanceof Error ? error.error.message : String(error.error);
  if (!/dynamically imported module|Importing a module script failed/i.test(message) || !navigator.onLine) return;
  let reloadedFor: string | null = null;
  try {
    reloadedFor = sessionStorage.getItem(RELOADED_KEY);
    sessionStorage.setItem(RELOADED_KEY, error.url);
  } catch {
    // Without storage, one reload is still better than a page that never opens.
  }
  if (reloadedFor !== error.url) inject(PAGE_LOCATION).assign(error.url);
}
