import { inject } from '@angular/core';
import { MatSnackBar, MatSnackBarRef, TextOnlySnackBar } from '@angular/material/snack-bar';
import { NavigationEnd, Router } from '@angular/router';
import { filter, first, takeUntil } from 'rxjs';

const INFO_MS = 4000;
/** Long enough to read the message and reach its action. */
const ACTION_MS = 10_000;

/**
 * Show a short message at the bottom of the screen. A message goes after a few seconds; one with an action stays
 * longer, and goes when the user moves to another page, where its action would no longer make sense.
 */
export function injectNotify(): (message: string, action?: string) => MatSnackBarRef<TextOnlySnackBar> {
  const snackBar = inject(MatSnackBar);
  const router = inject(Router);
  return (message, action) => {
    if (!action) return snackBar.open(message, undefined, { duration: INFO_MS });
    const ref = snackBar.open(message, action, { duration: ACTION_MS });
    const path = (url: string) => url.split(/[?#]/)[0];
    const openedOn = path(router.url);
    router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd && path(event.urlAfterRedirects) !== openedOn),
        first(),
        takeUntil(ref.afterDismissed()),
      )
      .subscribe(() => ref.dismiss());
    return ref;
  };
}
