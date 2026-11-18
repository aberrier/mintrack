import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { appRoutes, legacyRedirects } from './app.paths';
import { adminGuard, signedInGuard } from './core/auth/guards';

export { routesConfig };

const routesConfig: Routes = [
  { path: '', pathMatch: 'full', redirectTo: appRoutes.watchList() },
  { path: appRoutes.episodes(''), pathMatch: 'full', redirectTo: appRoutes.watchList() },
  // Keeps the query, such as /library?type=movie.
  ...Object.entries(legacyRedirects).map(([path, target]) => ({
    path,
    pathMatch: 'full' as const,
    redirectTo: ({ queryParams }: { queryParams: Record<string, string> }) =>
      inject(Router).createUrlTree([target], { queryParams }),
  })),
  {
    path: appRoutes.watchList(''),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/episodes/watch-list/watch-list'),
  },
  {
    path: appRoutes.upcoming(''),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/episodes/upcoming/upcoming'),
  },
  {
    path: appRoutes.discover(''),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/discover/discover'),
  },
  { path: appRoutes.login(undefined, ''), loadComponent: () => import('./pages/login/login') },
  { path: appRoutes.password(''), loadComponent: () => import('./pages/password/password') },
  { path: appRoutes.profile(''), canActivate: [signedInGuard], loadComponent: () => import('./pages/profile/profile') },
  {
    path: appRoutes.collection(''),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/profile/collection/collection'),
  },
  {
    path: appRoutes.adminUsers(''),
    canActivate: [signedInGuard, adminGuard],
    loadComponent: () => import('./pages/admin-users/admin-users'),
  },
  {
    path: appRoutes.show(':tmdbId', ''),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/show/show'),
  },
  {
    path: appRoutes.movie(':tmdbId', ''),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/movie/movie'),
  },
  { path: '**', redirectTo: appRoutes.watchList() },
];
