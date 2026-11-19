import { Page } from '@playwright/test';
import { Navigation } from '../drivers/pages';
import { expect, test } from '../dsl/fixtures';

test.use({ serviceWorkers: 'allow' });

/** Loads the app until its service worker controls the page and has cached the app shell. */
async function installApp(page: Page): Promise<void> {
  await page.goto('/');
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
  await expect
    .poll(() => page.evaluate(async () => (await caches.keys()).some((name) => name.includes(':assets:app:'))))
    .toBe(true);
}

test('the installed app opens without a network, but never answers the API from its cache', async ({
  admin: { page },
  context,
  consoleErrors,
}) => {
  await installApp(page);

  await context.setOffline(true);
  await page.goto('/login');

  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible();
  // The service worker answers 504 for a request it could only send to the network.
  expect(await page.evaluate(() => fetch('/api/health').then((response) => response.status))).toBe(504);

  // The only errors are those requests.
  expect(consoleErrors.every((error) => error.includes('504 (Gateway Timeout)'))).toBe(true);
  consoleErrors.length = 0;
});

test('the service worker leaves API pages to the server', async ({ admin: { page } }) => {
  await installApp(page);

  const response = await page.goto('/api/health');

  expect(response!.headers()['content-type']).toContain('application/json');
});

test('the settings explain that this server does not send notifications over plain HTTP', async ({
  admin: { page },
  browserName,
}) => {
  test.skip(browserName === 'webkit', 'WebKit for Linux has no Push API: Safari’s case is the next scenario');
  await new Navigation(page).openSettings();

  const settings = page.getByTestId('push-settings');
  await expect(settings.getByRole('switch', { name: 'Notify me on this device' })).toBeDisabled();
  await expect(settings.getByTestId('push-status')).toHaveText('This server needs an https address.');
});

test.describe('in a Safari tab on iPhone', () => {
  // The settings only need to know whether the browser has a Push API.
  test.use({ serviceWorkers: 'block' });

  test.beforeEach(async ({ context, browserName }) => {
    test.skip(browserName !== 'webkit', 'Safari on iOS');
    // Safari on iOS has no Push API in a tab, and says whether the page runs from the Home Screen.
    await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: false }));
  });

  test('the settings say to add the app to the Home Screen for notifications', async ({ admin: { page } }) => {
    await new Navigation(page).openSettings();

    const settings = page.getByTestId('push-settings');
    await expect(settings.getByRole('switch', { name: 'Notify me on this device' })).toBeDisabled();
    await expect(settings.getByTestId('push-status')).toHaveText('Add MinTrack to the Home Screen first.');
  });
});
