import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { AuthStore } from './auth.store';

export { adminGuard, safeNext, signedInGuard, signedOutOn401 };

/** Routes for signed-in users; others go to the login page, which brings them back afterwards. */
const signedInGuard: CanActivateFn = async (_route, state) => {
  const router = inject(Router);
  if (await inject(AuthStore).load()) return true;
  return router.parseUrl(appRoutes.login(state.url));
};

const adminGuard: CanActivateFn = async () => {
  const router = inject(Router);
  const user = await inject(AuthStore).load();
  return user?.is_admin ? true : router.parseUrl(appRoutes.home());
};

/**
 * A session that ended (expired, logged out elsewhere, user disabled) sends the app back to the login page.
 * Login answers 401 for a wrong password, and AuthStore.load reads the 401 of GET /api/auth/me as "signed out".
 */
const signedOutOn401: HttpInterceptorFn = (request, next) => {
  const store = inject(AuthStore);
  const router = inject(Router);
  return next(request).pipe(
    catchError((error: unknown) => {
      const handledByCaller =
        request.url === '/api/auth/login' || (request.method === 'GET' && request.url === '/api/auth/me');
      if (error instanceof HttpErrorResponse && error.status === 401 && !handledByCaller) {
        store.clear();
        void router.navigateByUrl(appRoutes.login(router.url));
      }
      return throwError(() => error);
    }),
  );
};

/** Only a path inside the app is followed after login, never another site. */
function safeNext(next: string | null | undefined): string {
  const inApp = next?.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\');
  return inApp ? next! : appRoutes.home();
}
