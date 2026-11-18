import { Routes } from '@angular/router';

export { appRoutes, routesConfig };

/** Every in-app URL, built here so links and routes cannot drift apart. */
const appRoutes = {
  home: (rp = '/') => `${rp}`,
};

const routesConfig: Routes = [
  {
    path: appRoutes.home(''),
    pathMatch: 'full',
    loadComponent: () => import('./pages/home/home'),
  },
  { path: '**', redirectTo: appRoutes.home() },
];
