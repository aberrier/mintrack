import { expect, test } from '../dsl/fixtures';

test('a signed-in user sees the app shell and that it is online', async ({ admin: { page } }) => {
  await expect(page.getByTestId('server-status')).toHaveText('Online');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page');
});

test('the bottom navigation stays on screen, with tap targets of at least 48px', async ({ admin: { page } }) => {
  const viewport = page.viewportSize()!;

  const nav = await page.getByTestId('bottom-nav').boundingBox();
  const home = await page.getByRole('link', { name: 'Home' }).boundingBox();

  expect(nav!.y + nav!.height).toBeLessThanOrEqual(viewport.height);
  expect(home!.height).toBeGreaterThanOrEqual(48);
  expect(home!.width).toBeGreaterThanOrEqual(48);
  // No horizontal scrolling on a phone.
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
});

test('client routes load the app', async ({ admin: { page } }) => {
  await page.goto('/shows/42');

  await expect(page.getByTestId('server-status')).toHaveText('Online');
});
