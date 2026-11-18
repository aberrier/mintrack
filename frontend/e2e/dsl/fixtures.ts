import { test as base, expect, Page } from '@playwright/test';
import { Account, signInAsNewAdmin } from './accounts';

interface Fixtures {
  consoleErrors: string[];
  /** A page signed in as a fresh admin. */
  admin: { page: Page; account: Account };
  /** A second, signed-out browser, for another person or another device. */
  otherPage: Page;
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
