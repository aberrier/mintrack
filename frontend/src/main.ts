import { bootstrapApplication } from '@angular/platform-browser';
import { App } from './app/app';
import { appConfig } from './app/app.config';
import { allowServiceWorkerScript } from './app/core/pwa/trusted-types';

allowServiceWorkerScript();
bootstrapApplication(App, appConfig).catch((error: unknown) => console.error(error));
