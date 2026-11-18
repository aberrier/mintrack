import { expect, Page } from '@playwright/test';

/** The pages of the app, as a user sees them: locators and actions only. */

export class Navigation {
  constructor(private readonly page: Page) {}

  bar() {
    return this.page.getByRole('navigation', { name: 'Main navigation' });
  }

  async openProfile(): Promise<void> {
    await this.bar().getByRole('link', { name: 'Profile' }).click();
    await expect(this.page.getByRole('button', { name: 'Log out', exact: true })).toBeVisible();
  }

  /** Open a URL typed in or bookmarked. */
  async openBookmark(path: string): Promise<void> {
    await this.page.goto(path);
  }

  /** Reload, as a user coming back later; true when the app is still signed in. */
  async reloadSignedIn(): Promise<boolean> {
    await this.page.reload();
    const login = this.page.getByRole('heading', { name: 'Log in' });
    await expect(login.or(this.bar())).toBeVisible();
    return this.bar().isVisible();
  }
}

export class LoginPage {
  constructor(private readonly page: Page) {}

  async waitShown(): Promise<void> {
    await expect(this.page.getByRole('heading', { name: 'Log in' })).toBeVisible();
  }

  /** Submit the form; true when the app signs in, false when it shows an error. */
  async logIn(username: string, password: string): Promise<boolean> {
    await this.page.getByLabel('Username').fill(username);
    await this.page.getByLabel('Password').fill(password);
    await this.page.getByRole('button', { name: 'Log in' }).click();
    const signedIn = new Navigation(this.page).bar();
    await expect(this.page.getByRole('alert').or(signedIn)).toBeVisible();
    return signedIn.isVisible();
  }
}

export class PasswordPage {
  constructor(private readonly page: Page) {}

  /** Open a link shared by the admin, as pasted in the address bar. */
  async open(link: string): Promise<void> {
    await this.page.goto(link);
    await expect(this.page.getByLabel('New password')).toBeVisible();
  }

  /** Open a link and report whether the page refuses it. */
  async visitRefused(link: string): Promise<boolean> {
    await this.page.goto(link);
    const refused = this.page.getByText('This link is invalid or has expired');
    await expect(refused.or(this.page.getByLabel('New password'))).toBeVisible();
    return refused.isVisible();
  }

  async accountName(): Promise<string> {
    return (await this.page.getByTestId('link-username').textContent())!.trim();
  }

  async setPassword(password: string): Promise<void> {
    await this.page.getByLabel('New password').fill(password);
    await this.page.getByRole('button', { name: 'Set password and log in' }).click();
    await expect(new Navigation(this.page).bar()).toBeVisible();
    // The token is gone from the address bar once read.
    await expect(this.page).not.toHaveURL(/#/);
  }
}

export class ProfilePage {
  constructor(private readonly page: Page) {}

  async isShown(): Promise<boolean> {
    const logOut = this.page.getByRole('button', { name: 'Log out', exact: true });
    await expect(logOut.or(this.page.getByTestId('server-status'))).toBeVisible();
    return logOut.isVisible();
  }

  async logOutEverywhere(): Promise<void> {
    await this.page.getByRole('button', { name: 'Log out everywhere' }).click();
    await expect(this.page.getByRole('heading', { name: 'Log in' })).toBeVisible();
  }

  async openUsers(): Promise<void> {
    await this.page.getByRole('link', { name: 'Manage users' }).click();
    await expect(this.page.getByRole('heading', { name: 'Users' })).toBeVisible();
  }
}

export class AdminUsersPage {
  constructor(private readonly page: Page) {}

  /** Invite a user and return the link shown once. */
  async invite(username: string): Promise<string> {
    await this.page.getByLabel('Username').fill(username);
    await this.page.getByRole('button', { name: 'Invite' }).click();
    return this.shownLink();
  }

  async newLink(username: string): Promise<string> {
    await this.row(username).getByRole('button', { name: 'New link' }).click();
    return this.shownLink();
  }

  async disable(username: string): Promise<void> {
    await this.row(username).getByRole('button', { name: 'Disable' }).click();
    await expect(this.row(username).getByTestId('status')).toHaveText('Disabled');
  }

  private row(username: string) {
    return this.page.locator(`[data-username="${username}"]`);
  }

  private async shownLink(): Promise<string> {
    const link = this.page.getByTestId('shown-link').getByTestId('link');
    await expect(link).toContainText('/password#');
    return (await link.textContent())!.trim();
  }
}

/** The API tokens section of the profile page. */
export class ApiTokensSection {
  constructor(private readonly page: Page) {}

  section() {
    return this.page.getByRole('region', { name: 'API tokens' });
  }

  /** Create a token and return its value, shown once. */
  async create(name: string): Promise<string> {
    await this.section().getByLabel('Token name').fill(name);
    await this.section().getByRole('button', { name: 'Create' }).click();
    const token = (await this.section().getByTestId('new-api-token').textContent())!.trim();
    await this.section().getByRole('button', { name: 'Done' }).click();
    return token;
  }

  row(name: string) {
    return this.section().getByRole('listitem').filter({ hasText: name });
  }

  async revoke(name: string): Promise<void> {
    await this.row(name).getByRole('button', { name: 'Revoke' }).click();
    await this.page.getByRole('dialog').getByRole('button', { name: 'Revoke' }).click();
    await expect(this.page.getByRole('dialog')).toHaveCount(0);
  }
}
