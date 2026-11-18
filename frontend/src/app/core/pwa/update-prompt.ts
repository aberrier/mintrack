import { DOCUMENT, inject, Injector } from '@angular/core';
import { SwUpdate } from '@angular/service-worker';
import { filter, map, merge } from 'rxjs';
import { injectTranslator, TranslationPath } from '../i18n';

/** Offers a reload when a new version is ready, or when the cached one can no longer run. */
export function promptForUpdates(): void {
  const updates = inject(SwUpdate);
  if (!updates.isEnabled) return;
  const injector = inject(Injector);
  const location = inject(DOCUMENT).location;
  const translate = injectTranslator('app');

  merge(
    updates.versionUpdates.pipe(
      filter((event) => event.type === 'VERSION_READY'),
      map((): TranslationPath<'app'> => 'app.update.ready'),
    ),
    updates.unrecoverable.pipe(map((): TranslationPath<'app'> => 'app.update.broken')),
  ).subscribe(async (message) => {
    // Loaded on first use: the snackbar stays out of the initial bundle.
    const { MatSnackBar } = await import('@angular/material/snack-bar');
    injector
      .get(MatSnackBar)
      .open(translate(message), translate('app.update.reload'))
      .onAction()
      .subscribe(() => location.reload());
  });
}
