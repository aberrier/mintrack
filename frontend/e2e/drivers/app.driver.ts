import { expect, Locator, Page } from '@playwright/test';

/** MinTrack's pages as a user reaches them: bottom navigation, links, buttons. Locators live only here. */
export class AppDriver {
  constructor(private readonly page: Page) {}

  async open(): Promise<void> {
    await this.page.goto('/');
    await expect(this.navigation()).toBeVisible();
  }

  /** Search from the bottom navigation and wait for the results. */
  async search(query: string): Promise<void> {
    await this.navigation().getByRole('link', { name: 'Search' }).click();
    // The field reacts to typing (debounced), like a user's keystrokes.
    await this.page.getByRole('searchbox', { name: 'Search shows and movies' }).pressSequentially(query);
    await expect(this.page.getByTestId('search-result').first()).toContainText(query);
  }

  /** Open a search result by its title and kind ("Show" or "Movie"). */
  async openResult(title: string, kind: 'Show' | 'Movie'): Promise<void> {
    await this.page.getByTestId('search-result').filter({ hasText: title }).filter({ hasText: kind }).click();
    await expect(this.page.getByRole('heading', { level: 1, name: title })).toBeVisible();
  }

  async clickButton(name: string): Promise<void> {
    await this.page.getByRole('button', { name, exact: true }).click();
  }

  status(testId: 'show-status' | 'movie-status'): Locator {
    return this.page.getByTestId(testId);
  }

  episode(season: number, episode: number): Locator {
    return this.page.getByRole('button', { name: `Season ${season}, episode ${episode}`, exact: true });
  }

  async toggleEpisode(season: number, episode: number): Promise<void> {
    const toggle = this.episode(season, episode);
    const pressed = await toggle.getAttribute('aria-pressed');
    await toggle.click();
    // The store updates the screen before the server answers.
    await expect(toggle).toHaveAttribute('aria-pressed', pressed === 'true' ? 'false' : 'true');
  }

  /** The snackbar offering to mark earlier episodes: returns its text, then accepts it. */
  async acceptPreviousOffer(): Promise<string> {
    const snackBar = this.page.locator('mat-snack-bar-container');
    const text = (await snackBar.locator('[matsnackbarlabel]').innerText()).trim();
    await snackBar.getByRole('button', { name: 'Mark watched' }).click();
    return text;
  }

  /** Open a season's menu (Material renders it in an overlay at the end of the page) and pick an item. */
  async seasonAction(season: number, action: string): Promise<void> {
    await this.page.getByRole('button', { name: `Actions for Season ${season}` }).click();
    await this.page.getByRole('menuitem', { name: action }).click();
  }

  async openLibrary(type: 'Shows' | 'Movies'): Promise<void> {
    await this.navigation().getByRole('link', { name: 'Library' }).click();
    await this.page.getByRole('link', { name: type, exact: true }).click();
    await expect(this.page.getByRole('heading', { level: 1, name: 'Library' })).toBeVisible();
  }

  libraryItem(title: string): Locator {
    return this.page.getByTestId('library-item').filter({ hasText: title });
  }

  /** The shell's content area, the only element that scrolls. */
  content(): Locator {
    return this.page.getByRole('main');
  }

  async back(): Promise<void> {
    await this.page.goBack();
  }

  private navigation(): Locator {
    return this.page.getByRole('navigation', { name: 'Main navigation' });
  }
}
