import { provideHttpClient, withFetch } from '@angular/common/http';
import { ApplicationConfig, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { routesConfig } from './app.routes';
import { registerIcons } from './core/icons/icons';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routesConfig),
    provideHttpClient(withFetch()),
    provideAppInitializer(registerIcons),
  ],
};
