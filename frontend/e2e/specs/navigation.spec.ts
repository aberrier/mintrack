import { logIn, openSignedOut } from '../dsl/accounts';
import { expect, test } from '../dsl/fixtures';
import {
  accessibilityViolations,
  activeTab,
  currentAddress,
  fitsTheScreen,
  offCentreIcons,
  openAddress,
  openEveryScreen,
  openWhileServerUnreachable,
  pageTitle,
  smallTargets,
  tabs,
} from '../dsl/navigation';

test('after login the app opens on Episodes › Watch list, with tabs of 48px, Admin for admins', async ({
  admin,
  otherPage,
}) => {
  // Given a signed-out visitor opening the app
  await openSignedOut(otherPage);

  // When they log in
  await logIn(otherPage, admin.account);

  // Then they are on the watch list, under the Episodes tab
  await expect(otherPage).toHaveURL(/\/episodes\/watch-list$/);
  expect(await activeTab(otherPage)).toBe('Episodes');
  const bar = await tabs(otherPage);
  expect(bar.map((tab) => tab.name)).toEqual(['Episodes', 'Discover', 'Profile', 'Admin']);
  for (const tab of bar) {
    expect(tab.height, tab.name).toBeGreaterThanOrEqual(48);
    expect(tab.bottom, tab.name).toBeLessThanOrEqual(otherPage.viewportSize()!.height);
  }
});

test('the root and unknown addresses lead to the watch list', async ({ admin: { page } }) => {
  const leadsTo = async (address: string, place: string) => {
    await openAddress(page, address);
    await expect.poll(() => currentAddress(page), address).toBe(place);
  };
  await leadsTo('/', '/episodes/watch-list');
  await leadsTo('/episodes', '/episodes/watch-list');
  await leadsTo('/no/such/page', '/episodes/watch-list');
  // Signed in, the login page leads home.
  await leadsTo('/login', '/episodes/watch-list');
});

test.describe('when the server cannot be reached', () => {
  test.use({ allowedConsoleErrors: [/ERR_FAILED/] });

  test('the app says so instead of a blank screen', async ({ page }) => {
    expect(await openWhileServerUnreachable(page)).toContain('MinTrack cannot be reached');
  });
});

// In parts that run in parallel, each checking every fourth screen.
const PARTS = 4;
for (let part = 0; part < PARTS; part++) {
  test(`every screen fits a 360px phone and the desktop, with 48px targets, centred icons and no accessibility violation (${part + 1}/${PARTS})`, async ({
    admin: { page },
  }, testInfo) => {
    if (testInfo.project.name === 'phone') await page.setViewportSize({ width: 360, height: 740 });

    const screens = (await openEveryScreen(page)).filter((_, index) => index % PARTS === part);
    for (const screen of screens) {
      await screen.open();
      await expect.poll(() => pageTitle(page), screen.name).toBe(screen.title);
      expect(await fitsTheScreen(page), screen.name).toBe(true);
      expect(await smallTargets(page), screen.name).toEqual([]);
      expect(await offCentreIcons(page), screen.name).toEqual([]);
      expect(await accessibilityViolations(page), screen.name).toEqual([]);
    }
  });
}
