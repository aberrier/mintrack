import {
  acceptLink,
  account,
  disable,
  invite,
  isLinkRefused,
  isOnProfile,
  isSignedInAfterReload,
  logIn,
  logOutEverywhere,
  newLink,
  openSignedOut,
  tryLogIn,
} from '../dsl/accounts';
import { expect, test } from '../dsl/fixtures';

test.describe('Accounts', () => {
  test('an invited user sets a password and lands on the home page', async ({ admin, otherPage }) => {
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

  test('a signed-out visitor logs in and gets the page they asked for', async ({ admin, otherPage }) => {
    // Given a signed-out visitor opening their profile
    await openSignedOut(otherPage, 'profile');

    // When they log in
    await logIn(otherPage, admin.account);

    // Then they are on their profile
    expect(await isOnProfile(otherPage)).toBe(true);
  });
});
