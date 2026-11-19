import { Routes } from '@angular/router';
import { appRoutes } from './app.paths';
import { adminGuard, signedInGuard, signedOutGuard } from './core/auth/guards';
import { TranslationPath } from './core/i18n';

export { routesConfig };

/** A page's title, translated by the app's title strategy; show and movie pages name themselves once loaded. */
const title = (path: TranslationPath<'app'>) => path;

const routesConfig: Routes = [
  { path: '', pathMatch: 'full', redirectTo: appRoutes.watchList() },
  { path: appRoutes.episodes(''), pathMatch: 'full', redirectTo: appRoutes.watchList() },
  {
    path: appRoutes.watchList(''),
    title: title('app.episodes.watchList'),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/episodes/watch-list/watch-list'),
  },
  {
    path: appRoutes.upcoming(''),
    title: title('app.episodes.upcoming'),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/episodes/upcoming/upcoming'),
  },
  {
    path: appRoutes.discover(''),
    title: title('app.nav.discover'),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/discover/discover'),
  },
  {
    path: appRoutes.login(undefined, ''),
    title: title('app.login.title'),
    canActivate: [signedOutGuard],
    loadComponent: () => import('./pages/login/login'),
  },
  {
    path: appRoutes.password(''),
    title: title('app.password.title'),
    loadComponent: () => import('./pages/password/password'),
  },
  {
    path: appRoutes.profile(''),
    title: title('app.nav.profile'),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/profile/profile'),
  },
  {
    path: appRoutes.collection(''),
    title: title('app.collection.title'),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/profile/collection/collection'),
  },
  {
    path: appRoutes.settings(''),
    title: title('app.profile.settings'),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/profile/settings/settings'),
  },
  {
    path: appRoutes.mcpHelp(''),
    title: title('app.mcpHelp.title'),
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/profile/mcp-help/mcp-help'),
  },
  {
    path: appRoutes.admin(''),
    title: title('app.nav.admin'),
    canActivate: [signedInGuard, adminGuard],
    loadComponent: () => import('./pages/admin/admin'),
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
