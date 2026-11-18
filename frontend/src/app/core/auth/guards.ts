import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { AuthStore } from './auth.store';

export { adminGuard, safeNext, signedInGuard, signedOutGuard, signedOutOn401 };

/**
 * Routes for signed-in users; others go to the login page, which brings them back afterwards. When the server cannot
 * say who is signed in (offline, down), the page stays closed and the shell says why.
 */
const signedInGuard: CanActivateFn = async (_route, state) => {
  const router = inject(Router);
  const store = inject(AuthStore);
  const user = await loadUser(store);
  if (user === undefined) {
    store.blockedUrl = state.url;
    return false;
  }
  return user ? true : router.parseUrl(appRoutes.login(state.url));
};

/** The login page is for signed-out visitors: a signed-in user goes to the watch list. */
const signedOutGuard: CanActivateFn = async () => {
  const router = inject(Router);
  const user = await loadUser(inject(AuthStore));
  return user ? router.parseUrl(appRoutes.watchList()) : true;
};

const adminGuard: CanActivateFn = async () => {
  const router = inject(Router);
  const user = await loadUser(inject(AuthStore));
  return user?.is_admin ? true : router.parseUrl(appRoutes.watchList());
};

/** The signed-in user, null when signed out, undefined when the server could not be asked. */
async function loadUser(store: AuthStore): Promise<Model.Http.User | null | undefined> {
  try {
    return await store.load();
  } catch {
    return undefined;
  }
}

/**
 * A session that ended (expired, logged out elsewhere, user disabled) reloads the app on the login page, so nothing
 * of the previous user stays in memory. Login answers 401 for a wrong password, and AuthStore.load reads the 401 of
 * GET /api/auth/me as "signed out".
 */
const signedOutOn401: HttpInterceptorFn = (request, next) => {
  const store = inject(AuthStore);
  const router = inject(Router);
  return next(request).pipe(
    catchError((error: unknown) => {
      const handledByCaller =
        request.url === '/api/auth/login' || (request.method === 'GET' && request.url === '/api/auth/me');
      if (error instanceof HttpErrorResponse && error.status === 401 && !handledByCaller && store.$user()) {
        store.clear();
        store.restartAt(appRoutes.login(router.url));
      }
      return throwError(() => error);
    }),
  );
};

/** Only a path inside the app is followed after login, never another site. */
function safeNext(next: string | null | undefined): string {
  const inApp = next?.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\');
  return inApp ? next! : appRoutes.watchList();
}
