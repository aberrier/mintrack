import { test as base, BrowserContext, expect, Page } from '@playwright/test';
import { ApiDriver } from '../drivers/api.driver';
import { AppDriver } from '../drivers/app.driver';
import { Account, signInAsNewAdmin } from './accounts';

/** Someone using MinTrack in the browser, signed in. */
export interface Viewer {
  app: AppDriver;
  api: ApiDriver;
}

interface Fixtures {
  /** Console errors a scenario causes on purpose, such as a server refusing a write. */
  allowedConsoleErrors: RegExp[];
  consoleErrors: string[];
  /** A page signed in as a fresh admin. */
  admin: { page: Page; account: Account };
  /** A second, signed-out browser, for another person or another device. */
  otherPage: Page;
  /** The signed-in admin's page, driven through the app and the API. */
  viewer: Viewer;
}

/** Every test fails on a console error or an uncaught exception, so a CSP violation breaks the build. */
export const test = base.extend<Fixtures>({
  context: async ({ context }, use) => {
    await asOwnDevice(context);
    await use(context);
  },
  allowedConsoleErrors: [[], { option: true }],
  consoleErrors: [
    async ({ page, allowedConsoleErrors }, use) => {
      const errors: string[] = [];
      // A page being left logs as errors the loads WebKit cancels for the next one: from its beforeunload, which the
      // page announces on the console, to the next page shown.
      let leaving = false;
      await page.addInitScript(
        (signal) => addEventListener('beforeunload', () => console.debug(signal)),
        LEAVING_SIGNAL,
      );
      page.on('domcontentloaded', () => (leaving = false));
      page.on('console', (message) => {
        if (message.text() === LEAVING_SIGNAL) leaving = true;
        const allowed = [...allowedConsoleErrors, ENGINE_NOTICE].some((pattern) => pattern.test(message.text()));
        if (
          message.type() === 'error' &&
          !allowed &&
          !leaving &&
          !isExpectedRefusal(message.text(), message.location().url)
        )
          errors.push(message.text());
      });
      page.on('pageerror', (error) => !leaving && errors.push(error.message));
      await use(errors);
      expect(errors, 'console errors').toEqual([]);
    },
    { auto: true },
  ],
  admin: async ({ page }, use) => {
    await use({ page, account: await signInAsNewAdmin(page) });
  },
  viewer: async ({ admin: { page } }, use) => {
    const app = new AppDriver(page);
    await app.open();
    await use({ app, api: new ApiDriver(page) });
  },
  otherPage: async ({ browser }, use) => {
    const context = await browser.newContext();
    await asOwnDevice(context);
    await use(await context.newPage());
    await context.close();
  },
});

/**
 * A browser as a device of its own: its own client address, which the test server trusts from its local proxy
 * (MINTRACK__SERVER__FORWARDED_ALLOW_IPS), so failed logins in one test never reach the per-address limit of the others;
 * and TMDB images served locally.
 */
async function asOwnDevice(context: BrowserContext): Promise<void> {
  const byte = () => Math.floor(Math.random() * 256);
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': `10.${byte()}.${byte()}.${byte()}` });
  await serveImagesLocally(context);
}

/** A grey pixel for every TMDB image: the fake TMDB's image paths exist nowhere, and tests stay offline. */
async function serveImagesLocally(context: BrowserContext): Promise<void> {
  const pixel = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    'base64',
  );
  await context.route('https://image.tmdb.org/**', (route) => route.fulfill({ contentType: 'image/png', body: pixel }));
}

/**
 * WebKit reports the viewport's interactive-widget key, which only Chromium reads (the on-screen keyboard resizes the
 * layout there), as an error.
 */
const ENGINE_NOTICE = /^Viewport argument key "interactive-widget" not recognized and ignored\.$/;
const LEAVING_SIGNAL = 'e2e: leaving the page';

/** Endpoints whose 400 is an answer the scenarios provoke: a wrong password, an invalid link, a refused Jellyfin. */
const REFUSING_ENDPOINTS = /\/api\/(auth\/(password|password-link|password-link\/use)|jellyfin\/[\w/-]+)$/;

/**
 * Chromium logs every 4xx response. Part of the scenarios: a 401 from the API (a refused login, an ended session) and
 * a 400 from the endpoints above; any other 4xx is a bug.
 */
function isExpectedRefusal(text: string, url: string): boolean {
  const status = /Failed to load resource: the server responded with a status of (\d{3})/.exec(text)?.[1];
  const path = url ? new URL(url).pathname : '';
  if (status === '401') return path.startsWith('/api/');
  return status === '400' && REFUSING_ENDPOINTS.test(path);
}

export { expect };
