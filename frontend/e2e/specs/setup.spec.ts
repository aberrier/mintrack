import {
  accountCreatedMeanwhile,
  createAdminAccount,
  isAdminSetupOffered,
  openFirstRun,
  signedOutHeading,
} from '../dsl/accounts';
import { expect, test } from '../dsl/fixtures';

test.describe('First run', () => {
  // The server refuses the admin account once one exists, which the browser logs.
  test.use({ allowedConsoleErrors: [/status of 409/] });

  test('a signed-out visitor is offered the admin account only while no account exists', async ({
    admin: _account,
    otherPage,
  }) => {
    // Given an account exists, a signed-out visitor only gets the login form
    expect(await isAdminSetupOffered(otherPage)).toBe(false);

    // When the server says no account exists yet, the admin account form shows
    expect(await openFirstRun(otherPage)).toBe(true);

    // Then a confirmation that differs is refused before anything is sent
    expect(await createAdminAccount(otherPage, 'a different e2e passphrase')).toBe('The passwords differ');

    // And once an account exists, creating the admin is refused and the login form comes back
    await accountCreatedMeanwhile(otherPage);
    expect(await createAdminAccount(otherPage)).toBe('The admin account already exists. Log in instead.');
    await expect.poll(() => signedOutHeading(otherPage)).toBe('Log in');
  });
});
