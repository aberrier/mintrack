import { bootstrapApplication } from '@angular/platform-browser';
import { App } from './app/app';
import { appConfig } from './app/app.config';
import { allowServiceWorkerScript } from './app/core/pwa/trusted-types';

// Safari on iOS applies :active, the press feedback, only under an element that listens to touches.
document.addEventListener('touchstart', () => undefined, { passive: true });
allowServiceWorkerScript();
bootstrapApplication(App, appConfig).catch((error: unknown) => console.error(error));
