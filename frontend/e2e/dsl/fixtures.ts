import { test as base, expect, Page } from '@playwright/test';
import { ApiDriver } from '../drivers/api.driver';
import { AppDriver } from '../drivers/app.driver';
import { Account, signInAsNewAdmin } from './accounts';

/** Someone using MinTrack in the browser, signed in. */
export interface Viewer {
  app: AppDriver;
  api: ApiDriver;
}

interface Fixtures {
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
  consoleErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error' && !isExpectedRefusal(message.text())) errors.push(message.text());
      });
      page.on('pageerror', (error) => errors.push(error.message));
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
    await use(await context.newPage());
    await context.close();
  },
});

/** Chromium logs every 4xx response; a refused login or an ended session is part of the scenarios. */
function isExpectedRefusal(text: string): boolean {
  return /Failed to load resource: the server responded with a status of (400|401)/.test(text);
}

export { expect };
