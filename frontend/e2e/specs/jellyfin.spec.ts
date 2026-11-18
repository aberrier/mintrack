import { Navigation } from '../drivers/pages';
import { expect, test } from '../dsl/fixtures';

test('linking a Jellyfin server MinTrack cannot reach says so and links nothing', async ({
  admin: { page },
  consoleErrors,
}) => {
  await new Navigation(page).openProfile();
  const jellyfin = page.getByRole('region', { name: 'Jellyfin' });
  await expect(jellyfin.getByTestId('jellyfin-empty')).toBeVisible();

  await jellyfin.getByLabel('Server address').fill('http://127.0.0.1:9');
  await jellyfin.getByLabel('Username').fill('bob');
  await jellyfin.getByLabel('Password').fill('secret');
  await jellyfin.getByRole('button', { name: 'Link', exact: true }).click();

  await expect(jellyfin.getByRole('alert')).toHaveText(/Cannot reach this server/);
  await expect(jellyfin.getByTestId('jellyfin-account')).toHaveCount(0);
  // A phone keeps the form inside the screen width.
  const viewport = page.viewportSize()!;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
  // The browser logs the API's 502 answer; it is the expected one.
  expect(consoleErrors).toEqual([expect.stringContaining('502')]);
  consoleErrors.length = 0;
});
