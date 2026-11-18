import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, isDevMode, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, TitleStrategy, withComponentInputBinding, withNavigationErrorHandler } from '@angular/router';
import { provideServiceWorker } from '@angular/service-worker';
import { routesConfig } from './app.routes';
import { signedOutOn401 } from './core/auth/guards';
import { registerIcons } from './core/icons/icons';
import { SERVICE_WORKER_SCRIPT } from './core/pwa/trusted-types';
import { promptForUpdates, reloadOnMissingChunk } from './core/pwa/update-prompt';
import { AppTitleStrategy } from './core/title';

// HttpClient's XSRF support is on by default: it echoes the XSRF-TOKEN cookie in X-XSRF-TOKEN on unsafe requests.
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routesConfig, withComponentInputBinding(), withNavigationErrorHandler(reloadOnMissingChunk)),
    { provide: TitleStrategy, useExisting: AppTitleStrategy },
    provideHttpClient(withFetch(), withInterceptors([signedOutOn401])),
    provideServiceWorker(SERVICE_WORKER_SCRIPT, {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
    provideAppInitializer(registerIcons),
    provideAppInitializer(promptForUpdates),
  ],
};
