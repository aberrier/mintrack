import { expect, Page } from '@playwright/test';
import { ApiDriver } from '../drivers/api.driver';
import { createAdmin } from '../drivers/cli';
import { AdminUsersPage, LoginPage, Navigation, PasswordPage, ProfilePage } from '../drivers/pages';

export interface Account {
  username: string;
  password: string;
}

export interface Invitation {
  username: string;
  link: string;
}

const PASSWORD = 'a long enough e2e passphrase';

/** A username no other test uses, so tests run in parallel and repeatedly on the same stack. */
export function unique(name: string): string {
  return `${name}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

export function account(username: string): Account {
  return { username, password: PASSWORD };
}

/**
 * An admin created with the CLI who set their password through the printed link, by the API: the password page has
 * its own scenarios (invitations, resets), so the other tests start on the home page without going through it.
 */
export async function signInAsNewAdmin(page: Page): Promise<Account> {
  const username = unique('admin');
  await new ApiDriver(page).usePasswordLink(createAdmin(username), PASSWORD);
  await new Navigation(page).openBookmark('/');
  await expect(new Navigation(page).bar()).toBeVisible();
  return account(username);
}

export async function invite(admin: Page, name = 'user'): Promise<Invitation> {
  const username = unique(name);
  await new Navigation(admin).openAdmin();
  return { username, link: await new AdminUsersPage(admin).invite(username) };
}

/** Open a password link and set the password; returns the account name the page showed. */
export async function acceptLink(page: Page, link: string): Promise<string> {
  const passwordPage = new PasswordPage(page);
  await passwordPage.open(link);
  const username = await passwordPage.accountName();
  await passwordPage.setPassword(PASSWORD);
  return username;
}

export async function isLinkRefused(page: Page, link: string): Promise<boolean> {
  return new PasswordPage(page).visitRefused(link);
}

export async function newLink(admin: Page, username: string): Promise<string> {
  return new AdminUsersPage(admin).newLink(username);
}

export async function disable(admin: Page, username: string): Promise<void> {
  await new AdminUsersPage(admin).disable(username);
}

/** Whether the Admin tab offers to disable the user. */
export async function canDisable(admin: Page, username: string): Promise<boolean> {
  return new AdminUsersPage(admin).offersDisable(username);
}

/** Open the app signed out at the given page, as from a bookmark; the login page shows. */
export async function openSignedOut(page: Page, where: 'home' | 'profile' = 'home'): Promise<void> {
  await new Navigation(page).openBookmark(where === 'home' ? '/' : '/profile');
  await new LoginPage(page).waitShown();
}

export async function logIn(page: Page, account: Account): Promise<void> {
  if (!(await tryLogIn(page, account))) throw new Error(`Login of ${account.username} was refused`);
}

/** Log in on the login page and report whether it worked. */
export async function tryLogIn(page: Page, account: Account): Promise<boolean> {
  return new LoginPage(page).logIn(account.username, account.password);
}

export async function logOutEverywhere(page: Page): Promise<void> {
  await new Navigation(page).openProfile();
  await new ProfilePage(page).logOutEverywhere();
}

export async function logOut(page: Page): Promise<void> {
  await new Navigation(page).openProfile();
  await new ProfilePage(page).logOut();
}

/** What the Profile tab's Shows row shows: titles, or the message for no show. */
export async function profileShows(page: Page): Promise<string> {
  await new Navigation(page).openProfile();
  return new ProfilePage(page).shows();
}

/** The bottom navigation's tabs. */
export async function tabNames(page: Page): Promise<string[]> {
  return new Navigation(page).tabNames();
}

/** Whether the app still lets the user in after they come back to it. */
export async function isSignedInAfterReload(page: Page): Promise<boolean> {
  return new Navigation(page).reloadSignedIn();
}

export async function isOnProfile(page: Page): Promise<boolean> {
  return new ProfilePage(page).isShown();
}
