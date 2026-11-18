import { Routes } from '@angular/router';
import { appRoutes } from './app.paths';
import { adminGuard, signedInGuard } from './core/auth/guards';

export { routesConfig };

const routesConfig: Routes = [
  {
    path: appRoutes.home(''),
    pathMatch: 'full',
    canActivate: [signedInGuard],
    loadComponent: () => import('./pages/home/home'),
  },
  { path: appRoutes.login(undefined, ''), loadComponent: () => import('./pages/login/login') },
  { path: appRoutes.password(''), loadComponent: () => import('./pages/password/password') },
  { path: appRoutes.profile(''), canActivate: [signedInGuard], loadComponent: () => import('./pages/profile/profile') },
  {
    path: appRoutes.adminUsers(''),
    canActivate: [signedInGuard, adminGuard],
    loadComponent: () => import('./pages/admin-users/admin-users'),
  },
  { path: appRoutes.library(''), canActivate: [signedInGuard], loadComponent: () => import('./pages/library/library') },
  { path: appRoutes.search(''), canActivate: [signedInGuard], loadComponent: () => import('./pages/search/search') },
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
  { path: '**', redirectTo: appRoutes.home() },
];
