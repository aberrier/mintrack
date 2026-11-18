export const SERVICE_WORKER_SCRIPT = 'ngsw-worker.js';

/**
 * Angular registers the service worker with a plain string, which the CSP's Trusted Types enforcement blocks.
 * The default policy turns that one URL, and nothing else, into a script URL; it creates no HTML or script.
 * Browsers without Trusted Types (Safari before 26) need nothing.
 */
export function allowServiceWorkerScript(): void {
  window.trustedTypes?.createPolicy('default', {
    createScriptURL: (url: string) => (url === SERVICE_WORKER_SCRIPT ? url : null),
  });
}
