import { logIn, openSignedOut } from '../dsl/accounts';
import { expect, test } from '../dsl/fixtures';
import {
  accessibilityViolations,
  activeTab,
  addressAfterOpening,
  fitsTheScreen,
  openEveryScreen,
  smallTargets,
  tabs,
} from '../dsl/navigation';

test('after login the app opens on Episodes › Watch list, with three tabs of 48px', async ({ admin, otherPage }) => {
  // Given a signed-out visitor opening the app
  await openSignedOut(otherPage);

  // When they log in
  await logIn(otherPage, admin.account);

  // Then they are on the watch list, under the Episodes tab
  await expect(otherPage).toHaveURL(/\/episodes\/watch-list$/);
  expect(await activeTab(otherPage)).toBe('Episodes');
  const bar = await tabs(otherPage);
  expect(bar.map((tab) => tab.name)).toEqual(['Episodes', 'Discover', 'Profile']);
  for (const tab of bar) {
    expect(tab.height, tab.name).toBeGreaterThanOrEqual(48);
    expect(tab.bottom, tab.name).toBeLessThanOrEqual(otherPage.viewportSize()!.height);
  }
});

test('old addresses lead to their new place', async ({ admin: { page } }) => {
  expect(await addressAfterOpening(page, '/')).toBe('/episodes/watch-list');
  expect(await addressAfterOpening(page, '/up-next')).toBe('/episodes/watch-list');
  expect(await addressAfterOpening(page, '/upcoming')).toBe('/episodes/upcoming');
  expect(await addressAfterOpening(page, '/library?type=movie')).toBe('/profile/collection?type=movie');
  expect(await addressAfterOpening(page, '/search')).toBe('/discover');
  expect(await addressAfterOpening(page, '/no/such/page')).toBe('/episodes/watch-list');
});

test('every screen fits a 360px phone and the desktop, with 48px targets and no accessibility violation', async ({
  admin: { page },
}, testInfo) => {
  if (testInfo.project.name === 'phone') await page.setViewportSize({ width: 360, height: 740 });

  for (const screen of await openEveryScreen(page)) {
    await screen.open();
    expect(await fitsTheScreen(page), screen.name).toBe(true);
    expect(await smallTargets(page), screen.name).toEqual([]);
    expect(await accessibilityViolations(page), screen.name).toEqual([]);
  }
});
