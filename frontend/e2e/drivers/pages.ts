import { expect, Page } from '@playwright/test';

/** The pages of the app, as a user sees them: locators and actions only. */

export class Navigation {
  constructor(private readonly page: Page) {}

  bar() {
    return this.page.getByRole('navigation', { name: 'Main navigation' });
  }

  async openProfile(): Promise<void> {
    await this.bar().getByRole('link', { name: 'Profile' }).click();
    await expect(this.settingsLink()).toBeVisible();
  }

  /** The Settings page, from the gear of the Profile tab. */
  async openSettings(): Promise<void> {
    await this.openProfile();
    await this.settingsLink().click();
    await expect(this.page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible();
  }

  settingsLink() {
    return this.page.getByRole('link', { name: 'Settings', exact: true });
  }

  /** The Admin tab, shown to admins only. */
  async openAdmin(): Promise<void> {
    await this.bar().getByRole('link', { name: 'Admin' }).click();
    await expect(this.page.getByRole('heading', { level: 1, name: 'Admin' })).toBeVisible();
  }

  async tabNames(): Promise<string[]> {
    await expect(this.bar()).toBeVisible();
    return (await this.bar().getByRole('link').allInnerTexts()).map((name) => name.trim());
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

/** The admin account form the login page shows instead while no account exists. */
export class SetupPage {
  constructor(private readonly page: Page) {}

  /** Open the app signed out; true when it offers to create the admin account once the server answered. */
  async isOffered(): Promise<boolean> {
    const answered = this.page.waitForResponse((response) => response.url().endsWith('/api/auth/setup'));
    await this.page.goto('/');
    await answered;
    const setup = this.page.getByRole('heading', { name: 'Create the admin account' });
    await expect(setup.or(this.page.getByRole('heading', { name: 'Log in' }))).toBeVisible();
    return setup.isVisible();
  }

  /** From now on the server seems to have no account yet; creating one still reaches the server. */
  async pretendNoAccount(): Promise<void> {
    await this.page.route('/api/auth/setup', (route) =>
      route.request().method() === 'GET' ? route.fulfill({ json: { open: true } }) : route.fallback(),
    );
  }

  async stopPretending(): Promise<void> {
    await this.page.unroute('/api/auth/setup');
  }

  /** Fill and submit the form; returns the message it shows (a field error or an alert). */
  async create(username: string, password: string, confirm: string): Promise<string> {
    await this.page.getByLabel('Username').fill(username);
    await this.page.getByLabel('Password', { exact: true }).fill(password);
    await this.page.getByLabel('Confirm password').fill(confirm);
    await this.page.getByRole('button', { name: 'Create the admin account' }).click();
    const message = this.page.getByRole('alert').or(this.page.locator('mat-error')).first();
    await expect(message).toBeVisible();
    return (await message.innerText()).trim();
  }

  /** The heading shown now: the admin account form or the login form. */
  async heading(): Promise<string> {
    const heading = this.page.getByRole('heading', { level: 1 });
    await expect(heading).toBeVisible();
    return (await heading.innerText()).trim();
  }
}

export class PasswordPage {
  constructor(private readonly page: Page) {}

  /** Open a link shared by the admin, as pasted in the address bar. */
  async open(link: string): Promise<void> {
    await this.page.goto(link);
    await expect(this.page.getByLabel('New password')).toBeVisible();
  }

  /** Load the page again, as a restored tab or a pull to refresh does; the form shows again. */
  async reload(): Promise<void> {
    await this.page.reload();
    await expect(this.page.getByLabel('New password')).toBeVisible();
  }

  /** Open a link and return why the page refuses it, or null when it offers to set the password. */
  async visitRefusal(link: string): Promise<string | null> {
    await this.page.goto(link);
    const refused = this.page.getByRole('alert');
    await expect(refused.or(this.page.getByLabel('New password'))).toBeVisible();
    return (await refused.isVisible()) ? (await refused.textContent())!.trim() : null;
  }

  /** Whether the refused link's page offers to log in. */
  async offersLogIn(): Promise<boolean> {
    return this.page.getByRole('link', { name: 'Log in' }).isVisible();
  }

  async accountName(): Promise<string> {
    return (await this.page.getByTestId('link-username').textContent())!.trim();
  }

  async setPassword(password: string): Promise<void> {
    await this.page.getByLabel('New password').fill(password);
    await this.page.getByRole('button', { name: 'Set password and log in' }).click();
    await expect(new Navigation(this.page).bar()).toBeVisible();
    // The app moves on to the watch list, replacing the address that held the token.
    await expect(this.page).toHaveURL(/\/episodes\/watch-list$/);
  }
}

export class ProfilePage {
  constructor(private readonly page: Page) {}

  async isShown(): Promise<boolean> {
    const settings = new Navigation(this.page).settingsLink();
    await expect(settings.or(this.page.getByTestId('watch-list'))).toBeVisible();
    return settings.isVisible();
  }

  async logOutEverywhere(): Promise<void> {
    await this.page.getByRole('button', { name: 'Log out everywhere' }).click();
    await expect(this.page.getByRole('heading', { name: 'Log in' })).toBeVisible();
  }

  async logOut(): Promise<void> {
    await this.page.getByRole('button', { name: 'Log out', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Log in' })).toBeVisible();
  }

  /** The titles of the Shows row, or its empty message. */
  async shows(): Promise<string> {
    const row = this.page.getByRole('region', { name: 'Shows' });
    const items = row.getByTestId('profile-item');
    await expect(items.first().or(row.getByText('No shows yet'))).toBeVisible();
    return (await row.innerText()).trim();
  }
}

/** The Connected devices section of the settings. */
export class DevicesSection {
  constructor(private readonly page: Page) {}

  private devices() {
    return this.page.getByTestId('device');
  }

  /** Each device as listed: its name, then "This device" or when it was last active. */
  async list(): Promise<string[]> {
    await expect(this.devices().first()).toBeVisible();
    return (await this.devices().allInnerTexts()).map((text) =>
      text.replace(/\s+/g, ' ').replace(' Log out', '').trim(),
    );
  }

  /** Log out the first device other than this one. */
  async logOutAnother(): Promise<void> {
    const count = await this.devices().count();
    await this.devices()
      .getByRole('button', { name: /^Log out / })
      .first()
      .click();
    await expect(this.devices()).toHaveCount(count - 1);
  }
}

export class AdminUsersPage {
  constructor(private readonly page: Page) {}

  /** Invite a user and return the link shown once. */
  async invite(username: string): Promise<string> {
    await this.page.getByLabel('Username').fill(username);
    await this.page.getByRole('button', { name: 'Invite' }).click();
    return this.shownLink(username);
  }

  async newLink(username: string): Promise<string> {
    const previous = (await this.linkText().count()) ? await this.linkText().textContent() : null;
    await this.row(username).getByRole('button', { name: 'New link' }).click();
    // The box may still show the previous link until the new one arrives.
    if (previous) await expect(this.linkText()).not.toHaveText(previous);
    return this.shownLink(username);
  }

  async disable(username: string): Promise<void> {
    await this.row(username).getByRole('button', { name: 'Disable' }).click();
    await expect(this.row(username).getByTestId('status')).toHaveText('Disabled');
  }

  /** Whether the user's row offers Disable. */
  async offersDisable(username: string): Promise<boolean> {
    await expect(this.row(username)).toBeVisible();
    return (await this.row(username).getByRole('button', { name: 'Disable' }).count()) > 0;
  }

  /** Type in the user search; returns the names listed once the list follows. */
  async search(text: string): Promise<string[]> {
    await this.page.getByLabel('Search users').fill(text);
    const rows = this.page.getByTestId('users').getByRole('listitem');
    await expect(rows.first().or(this.page.getByTestId('no-user'))).toBeVisible();
    return rows.evaluateAll((items) => items.map((item) => item.getAttribute('data-username')!));
  }

  private row(username: string) {
    return this.page.locator(`[data-username="${username}"]`);
  }

  private linkText() {
    return this.page.getByTestId('shown-link').getByTestId('link');
  }

  private async shownLink(username: string): Promise<string> {
    await expect(this.page.getByTestId('shown-link')).toContainText(`Send this link to ${username}.`);
    await expect(this.linkText()).toContainText('/password#');
    await expect(this.page.getByTestId('link-validity')).toContainText('Valid until');
    return (await this.linkText().textContent())!.trim();
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

  /** Where a token's value would show, once created. */
  shown(token: string) {
    return this.page.getByText(token);
  }

  createButton() {
    return this.section().getByRole('button', { name: 'Create' });
  }

  async revoke(name: string): Promise<void> {
    await this.row(name).getByRole('button', { name: 'Revoke' }).click();
    await this.page.getByRole('dialog').getByRole('button', { name: 'Revoke' }).click();
    await expect(this.page.getByRole('dialog')).toHaveCount(0);
  }
}

/** The import card of the profile. */
export class ImportsSection {
  constructor(private readonly page: Page) {}

  /**
   * The import API as the server answers it: no import yet, then the uploaded job's states, one per read. Returns the
   * bodies of the uploads.
   */
  async serveImports(states: object[]): Promise<{ uploads: string[] }> {
    const uploads: string[] = [];
    let latest: object | null = null;
    await this.page.route('/api/imports/latest', (route) => {
      if (latest !== null && states.length) latest = states.shift()!;
      return route.fulfill({ json: latest });
    });
    await this.page.route('/api/imports', (route) => {
      uploads.push(route.request().postData() ?? '');
      latest = states.shift()!;
      return route.fulfill({ status: 202, json: latest });
    });
    return { uploads };
  }

  async upload(file: { name: string; mimeType: string; buffer: Buffer }): Promise<void> {
    await this.page.getByTestId('import-file').setInputFiles(file);
  }

  async chooseSource(name: 'Yamtrack' | 'TV Time'): Promise<void> {
    await this.source(name).click();
  }

  source(name: 'Yamtrack' | 'TV Time') {
    return this.page.getByRole('radio', { name });
  }

  chooseFile() {
    return this.page.getByRole('button', { name: 'Choose a file and import' });
  }

  status() {
    return this.page.getByTestId('import-status');
  }

  report() {
    return this.page.getByTestId('import-report');
  }

  /** The report's folded warnings: "Warnings (n)", opening on a tap. */
  warnings() {
    return this.page.getByTestId('import-warnings').locator('summary');
  }

  /** A line of the card, such as a file name to upload or an unmatched title. */
  line(text: string) {
    return this.page.getByText(text);
  }
}

/** The Jellyfin card of the profile: linked accounts and the link form, Quick Connect first. */
export class JellyfinSection {
  constructor(private readonly page: Page) {}

  section() {
    return this.page.getByRole('region', { name: 'Jellyfin' });
  }

  async waitShown(): Promise<void> {
    await expect(this.section().getByTestId('jellyfin-empty')).toBeVisible();
  }

  /** Ask for a Quick Connect code for the server at `address`. */
  async getCode(address: string): Promise<void> {
    await this.section().getByLabel('Server address').fill(address);
    await this.section().getByRole('button', { name: 'Get a code' }).click();
  }

  /** The code to approve in Jellyfin, once shown. */
  async code(): Promise<string> {
    const code = this.section().getByTestId('quick-connect-code');
    await expect(code).toBeVisible();
    return (await code.innerText()).trim();
  }

  async error(): Promise<string> {
    const alert = this.section().getByRole('alert');
    await expect(alert).toBeVisible();
    return (await alert.innerText()).trim();
  }

  accounts() {
    return this.section().getByTestId('jellyfin-account');
  }

  /**
   * A Jellyfin server with Quick Connect, as MinTrack's API reports it: a code, approved at the second question,
   * then the linked account.
   */
  async serveQuickConnect(account: { username: string; server_url: string }): Promise<void> {
    let asked = 0;
    await this.page.route('/api/jellyfin/quick-connect', (route) =>
      route.fulfill({ json: { code: '424242', secret: 'e2e-secret' } }),
    );
    await this.page.route('/api/jellyfin/quick-connect/state', (route) =>
      route.fulfill({ json: { approved: ++asked >= 2 } }),
    );
    await this.page.route('/api/jellyfin/accounts/quick-connect', (route) =>
      route.fulfill({
        status: 201,
        json: {
          id: 'e2e-account',
          ...account,
          last_sync_at: null,
          last_success_at: null,
          last_sync_status: null,
          last_sync_imported: 0,
          last_sync_skipped: 0,
          last_sync_unmatched: [],
        },
      }),
    );
  }

  /** A linked account, as MinTrack's API reports it, whose last full sync did not recognize these movies. */
  async serveAccountWithUnrecognized(movies: { name: string; year: number }[]): Promise<void> {
    const now = new Date().toISOString();
    const unmatched = movies.map(({ name, year }) => ({
      name,
      type: 'Movie',
      year,
      provider_ids: {},
      series_name: null,
      series_year: null,
      series_provider_ids: null,
      season: null,
      episode: null,
      reason: 'not_found',
    }));
    const account = {
      id: 'e2e-account',
      server_url: 'https://jellyfin.example.com',
      username: 'bob',
      last_sync_at: now,
      last_success_at: now,
      last_sync_status: 'ok',
      last_sync_imported: 0,
      last_sync_skipped: unmatched.length,
      last_sync_unmatched: unmatched,
    };
    await this.page.route('/api/jellyfin/accounts', (route) => route.fulfill({ json: [account] }));
  }

  /** Copy the details of the items not recognized; returns what the app then says. */
  async copyDetails(): Promise<string> {
    await this.accounts().getByRole('button', { name: 'Copy details' }).click();
    const snackBar = this.page.locator('mat-snack-bar-container');
    await expect(snackBar).toBeVisible();
    return (await snackBar.innerText()).trim();
  }
}
