import {
  acceptLink,
  account,
  canDisable,
  connectedDevices,
  disable,
  invite,
  isLinkRefused,
  isOnProfile,
  isSignedInAfterReload,
  logIn,
  logOut,
  logOutEverywhere,
  newLink,
  openSignedOut,
  profileShows,
  signOutOtherDevice,
  tabNames,
  tryLogIn,
} from '../dsl/accounts';
import { expect, test } from '../dsl/fixtures';
import { uniqueTitle } from '../dsl/tracking';

test.describe('Accounts', () => {
  test('an invited user sets a password and lands on the watch list', async ({ admin, otherPage }) => {
    // Given an admin invited a user
    const invitation = await invite(admin.page);

    // When the user opens the link and sets a password
    const shownAccount = await acceptLink(otherPage, invitation.link);

    // Then the link named their account, and they are signed in, also after coming back
    expect(shownAccount).toBe(invitation.username);
    expect(await isSignedInAfterReload(otherPage)).toBe(true);
  });

  test('admin resets and disables a user', async ({ admin, otherPage }) => {
    // Given a user who accepted their invitation
    const invitation = await invite(admin.page);
    await acceptLink(otherPage, invitation.link);

    // When the admin gives them a new link, then disables them
    const reset = await newLink(admin.page, invitation.username);
    await disable(admin.page, invitation.username);

    // Then their session has ended, they cannot log in, and the new link is refused
    expect(await isSignedInAfterReload(otherPage)).toBe(false);
    expect(await tryLogIn(otherPage, account(invitation.username))).toBe(false);
    expect(await isLinkRefused(otherPage, reset)).toBe(true);

    // And the admin is never offered to disable their own account, which would lock them out
    expect(await canDisable(admin.page, admin.account.username)).toBe(false);
  });

  test('user logs out everywhere', async ({ admin, otherPage }) => {
    // Given the admin is also signed in on another device
    await openSignedOut(otherPage);
    await logIn(otherPage, admin.account);

    // When they log out everywhere from the first device
    await logOutEverywhere(admin.page);

    // Then the other device is signed out too
    expect(await isSignedInAfterReload(otherPage)).toBe(false);
  });

  test('user sees their connected devices and signs one out', async ({ admin, otherPage }) => {
    // Given the admin is also signed in on another device
    await openSignedOut(otherPage);
    await logIn(otherPage, admin.account);

    // When they open their connected devices
    const devices = await connectedDevices(admin.page);

    // Then this device comes first, then the other one with when it was last active
    expect(devices).toEqual([expect.stringMatching(/ This device$/), expect.stringMatching(/ Last active /)]);

    // And signing the other one out ends its session only
    await signOutOtherDevice(admin.page);
    expect(await isSignedInAfterReload(otherPage)).toBe(false);
    expect(await isSignedInAfterReload(admin.page)).toBe(true);
  });

  test('the next person to log in on the same tab sees nothing of the previous one', async ({
    admin,
    viewer,
    otherPage,
  }) => {
    // Given the admin follows a show and saw it on their profile, and invited someone who set a password
    const show = uniqueTitle('Private Pier');
    await viewer.api.markWatched(show, [[1, 1]]);
    expect(await profileShows(admin.page)).toContain(show);
    const invitation = await invite(admin.page);
    await acceptLink(otherPage, invitation.link);

    // When the admin logs out and the other person logs in on the same tab
    await logOut(admin.page);
    await logIn(admin.page, account(invitation.username));

    // Then none of the admin's shows shows, nor the Admin tab
    const shows = await profileShows(admin.page);
    expect(shows).toContain('No shows yet');
    expect(shows).not.toContain(show);
    expect(await tabNames(admin.page)).toEqual(['Episodes', 'Discover', 'Profile']);
  });

  test('a signed-out visitor logs in and gets the page they asked for', async ({ admin, otherPage }) => {
    // Given a signed-out visitor opening their profile
    await openSignedOut(otherPage, 'profile');

    // When they log in
    await logIn(otherPage, admin.account);

    // Then they are on their profile
    expect(await isOnProfile(otherPage)).toBe(true);
  });
});
