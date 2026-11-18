import { McpDriver } from '../drivers/mcp.driver';
import { ApiTokensSection, Navigation } from '../drivers/pages';
import { unique } from '../dsl/accounts';
import { expect, test } from '../dsl/fixtures';

test('someone connects an assistant with an API token, then revokes it', async ({ admin: { page }, request }) => {
  const name = unique('Assistant');
  const mcp = new McpDriver(request);
  const tokens = new ApiTokensSection(page);
  await new Navigation(page).openProfile();

  const token = await tokens.create(name);

  expect(token).toMatch(/^mt_[\w-]{43}$/);
  expect(await mcp.initialize(token)).toEqual({ status: 200, serverName: 'MinTrack' });
  await page.reload();
  await expect(tokens.row(name)).toContainText('last used');
  await expect(page.getByText(token)).toHaveCount(0);

  await tokens.revoke(name);

  await expect(tokens.row(name)).toHaveCount(0);
  expect(await mcp.initialize(token)).toEqual({ status: 401 });
});

test('the API tokens section fits a phone, with tap targets of at least 48px', async ({ admin: { page } }) => {
  await new Navigation(page).openProfile();

  const create = await new ApiTokensSection(page).section().getByRole('button', { name: 'Create' }).boundingBox();

  expect(create!.height).toBeGreaterThanOrEqual(48);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()!.width,
  );
});
