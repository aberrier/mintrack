import { JellyfinSection, Navigation } from '../drivers/pages';
import { expect, test } from '../dsl/fixtures';

test('linking a Jellyfin server MinTrack cannot reach says so and links nothing', async ({
  admin: { page },
  consoleErrors,
}) => {
  await new Navigation(page).openProfile();
  const jellyfin = new JellyfinSection(page);
  await jellyfin.waitShown();

  await jellyfin.getCode('http://127.0.0.1:9');

  expect(await jellyfin.error()).toMatch(/Cannot reach this server/);
  await expect(jellyfin.accounts()).toHaveCount(0);
  // A phone keeps the form inside the screen width.
  const viewport = page.viewportSize()!;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
  // The browser logs the API's 502 answer; it is the expected one.
  expect(consoleErrors).toEqual([expect.stringContaining('502')]);
  consoleErrors.length = 0;
});

test('Quick Connect shows a code to approve in Jellyfin, then links the account without a password', async ({
  admin: { page },
}) => {
  await new Navigation(page).openProfile();
  const jellyfin = new JellyfinSection(page);
  await jellyfin.waitShown();
  await jellyfin.serveQuickConnect({ username: 'bob', server_url: 'https://jellyfin.example.com' });

  await jellyfin.getCode('https://jellyfin.example.com');

  expect(await jellyfin.code()).toBe('424242');
  await expect(jellyfin.accounts()).toContainText('bob', { timeout: 10_000 });
});
