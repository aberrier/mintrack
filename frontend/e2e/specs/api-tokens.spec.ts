import { McpDriver } from '../drivers/mcp.driver';
import { ApiTokensSection, Navigation } from '../drivers/pages';
import { ScreenDriver } from '../drivers/screen.driver';
import { unique } from '../dsl/accounts';
import { expect, test } from '../dsl/fixtures';

test('someone connects an assistant with an API token, then revokes it', async ({ admin: { page }, request }) => {
  const name = unique('Assistant');
  const mcp = new McpDriver(request);
  const tokens = new ApiTokensSection(page);
  await new Navigation(page).openSettings();

  const token = await tokens.create(name);

  expect(token).toMatch(/^mt_[\w-]{43}$/);
  expect(await mcp.initialize(token)).toEqual({ status: 200, serverName: 'MinTrack' });
  await new Navigation(page).reloadSignedIn();
  await expect(tokens.row(name)).toContainText('last used');
  await expect(tokens.shown(token)).toHaveCount(0);

  await tokens.revoke(name);

  await expect(tokens.row(name)).toHaveCount(0);
  expect(await mcp.initialize(token)).toEqual({ status: 401 });
});

test('the API tokens section fits a phone, with tap targets of at least 48px', async ({ admin: { page } }) => {
  await new Navigation(page).openSettings();

  const create = await new ApiTokensSection(page).createButton().boundingBox();

  expect(create!.height).toBeGreaterThanOrEqual(48);
  expect(await new ScreenDriver(page).fitsWidth()).toBe(true);
});
