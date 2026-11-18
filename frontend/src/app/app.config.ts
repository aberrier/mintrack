import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { routesConfig } from './app.routes';
import { signedOutOn401 } from './core/auth/guards';
import { registerIcons } from './core/icons/icons';

// HttpClient's XSRF support is on by default: it echoes the XSRF-TOKEN cookie in X-XSRF-TOKEN on unsafe requests.
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routesConfig, withComponentInputBinding()),
    provideHttpClient(withFetch(), withInterceptors([signedOutOn401])),
    provideAppInitializer(registerIcons),
  ],
};
