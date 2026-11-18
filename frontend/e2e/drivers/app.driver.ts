import { expect, Locator, Page } from '@playwright/test';

export type Tab = 'Episodes' | 'Discover' | 'Profile';

/** MinTrack's pages as a user reaches them: bottom navigation, links, buttons. Locators live only here. */
export class AppDriver {
  constructor(private readonly page: Page) {}

  async open(): Promise<void> {
    await this.page.goto('/');
    await expect(this.navigation()).toBeVisible();
  }

  async openTab(tab: Tab): Promise<void> {
    await this.navigation().getByRole('link', { name: tab }).click();
  }

  /** Search from the Discover tab, among shows or movies, and wait for the results. */
  async search(query: string, type: 'Shows' | 'Movies' = 'Shows'): Promise<void> {
    await this.openTab('Discover');
    await this.page.getByRole('link', { name: type, exact: true }).click();
    // The field reacts to typing (debounced), like a user's keystrokes.
    await this.page.getByRole('searchbox', { name: 'Search shows and movies' }).pressSequentially(query);
    await expect(this.page.getByTestId('search-result').first()).toContainText(query);
  }

  /** Open a search result by its title. */
  async openResult(title: string): Promise<void> {
    await this.searchResult(title).getByRole('link', { name: title }).click();
    await expect(this.page.getByRole('heading', { level: 1, name: title })).toBeVisible();
  }

  searchResult(title: string): Locator {
    return this.page.getByTestId('search-result').filter({ hasText: title });
  }

  url(): string {
    return this.page.url();
  }

  /** Open a show's or a movie's page, as from a link shared or bookmarked. */
  async openShowPage(tmdbId: number): Promise<void> {
    await this.page.goto(`/shows/${tmdbId}`);
    await expect(this.status('show-status')).toBeVisible();
  }

  async openMoviePage(tmdbId: number): Promise<void> {
    await this.page.goto(`/movies/${tmdbId}`);
    await expect(this.movieCheck()).toBeVisible();
  }

  async reload(): Promise<void> {
    await this.page.reload();
    await expect(this.navigation()).toBeVisible();
  }

  /** The open page's settings, by their headings and buttons, in order. */
  async settings(): Promise<string[]> {
    const region = this.page.getByRole('region', { name: 'Settings' });
    await expect(region).toBeVisible();
    return region
      .locator('h2, h3, mat-label, button, a[href]')
      .evaluateAll((elements) => elements.map((element) => element.textContent!.trim()).filter(Boolean));
  }

  heading(): Locator {
    return this.page.getByRole('heading', { level: 1 });
  }

  /** Hold the requests whose URL ends with `suffix` until `release` settles, as on a slow network. */
  async holdRequests(suffix: string, release: Promise<void>): Promise<void> {
    await this.page.route(
      (url) => url.pathname.endsWith(suffix),
      async (route) => {
        await release;
        await route.continue();
      },
    );
  }

  /** The next response to a request whose URL ends with `suffix`. */
  nextResponse(suffix: string): Promise<unknown> {
    return this.page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(suffix));
  }

  searchResults(): Locator {
    return this.page.getByTestId('search-result');
  }

  /** How many posters a row of the search results holds. */
  async resultColumns(): Promise<number> {
    return this.page
      .getByRole('list', { name: 'Results' })
      .evaluate((list) => getComputedStyle(list).gridTemplateColumns.split(' ').length);
  }

  /** The Discover tab's Shows or Movies, as the URL keeps it. */
  async chooseDiscoverType(type: 'Shows' | 'Movies'): Promise<string> {
    await this.page
      .getByRole('navigation', { name: 'Shows or movies' })
      .getByRole('link', { name: type, exact: true })
      .click();
    await expect(this.page.getByRole('link', { name: type, exact: true })).toHaveAttribute('aria-current', 'page');
    return new URL(this.page.url()).search;
  }

  /** Discover without a query: a row of trending titles, such as "Trending shows". */
  trendingRow(name: string): Locator {
    return this.page.getByRole('region', { name });
  }

  /** The `+` of a poster, then a check once the title is in the library. */
  posterAdd(within: Locator, title: string): Locator {
    return within.getByRole('button', { name: `Add ${title}`, exact: true });
  }

  posterAdded(within: Locator, title: string): Locator {
    return within.getByRole('button', { name: `${title}, in your library`, exact: true });
  }

  finishedBadge(within: Locator): Locator {
    return within.getByTestId('finished-badge');
  }

  async clickButton(name: string): Promise<void> {
    await this.page.getByRole('button', { name, exact: true }).click();
  }

  status(testId: 'show-status' | 'movie-status'): Locator {
    return this.page.getByTestId(testId);
  }

  /** The header's line of facts, such as "2 seasons · Channel Nine". */
  mediaFacts(): Locator {
    return this.page.getByTestId('media-facts');
  }

  /** The movie page's line saying when it was watched, or that it was not. */
  movieWatched(): Locator {
    return this.page.getByTestId('movie-watched');
  }

  movieCheck(): Locator {
    return this.page.getByRole('button', { name: 'Mark watched', exact: true });
  }

  /** The show page's tabs, About and Episodes. */
  async openShowTab(name: 'About' | 'Episodes'): Promise<void> {
    await this.page.getByRole('navigation', { name: 'Show sections' }).getByRole('link', { name }).click();
  }

  watchNext(): Locator {
    return this.page.getByTestId('watch-next');
  }

  async checkWatchNext(): Promise<void> {
    await this.watchNext()
      .getByRole('button', { name: /^Mark .* watched$/ })
      .click();
  }

  seasonToggle(season: number): Locator {
    return this.page.getByRole('button', { name: new RegExp(`^Season ${season} \\d+/\\d+$`) });
  }

  /** A season's check: marks its aired episodes, or asks to unmark it once all are watched. */
  seasonCheck(season: number): Locator {
    return this.page.getByRole('button', { name: `Mark Season ${season} watched`, exact: true });
  }

  /** A season row's `watched/aired`. */
  async seasonProgress(season: number): Promise<string> {
    return (await this.seasonToggle(season).getByTestId('season-progress').innerText()).trim();
  }

  /** Answer the open confirmation dialog with one of its buttons. */
  async answerDialog(button: string): Promise<void> {
    await this.page.getByRole('dialog').getByRole('button', { name: button }).click();
    await expect(this.page.getByRole('dialog')).toHaveCount(0);
  }

  confetti(): Locator {
    return this.page.getByTestId('confetti');
  }

  episode(season: number, episode: number): Locator {
    return this.page.getByRole('button', { name: `Season ${season}, episode ${episode}`, exact: true });
  }

  /** Open a season to its episodes, unless it is open. */
  async openSeason(season: number): Promise<void> {
    const toggle = this.seasonToggle(season);
    if ((await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click();
  }

  async toggleEpisode(season: number, episode: number): Promise<void> {
    await this.openSeason(season);
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

  snackBar(): Locator {
    return this.page.locator('mat-snack-bar-container');
  }

  /** The Profile tab's row of shows or movies. */
  profileRow(type: 'Shows' | 'Movies'): Locator {
    return this.page.getByRole('region', { name: type });
  }

  profileItem(type: 'Shows' | 'Movies', title: string): Locator {
    return this.profileRow(type).getByTestId('profile-item').filter({ hasText: title });
  }

  /** All the user's shows or movies, from See all on the Profile tab. */
  async openLibrary(type: 'Shows' | 'Movies'): Promise<void> {
    await this.openTab('Profile');
    await this.profileRow(type).getByRole('link', { name: 'See all' }).click();
    await expect(this.page.getByRole('heading', { level: 1, name: type })).toBeVisible();
  }

  /** Pick a choice of the library's Sort by or Progress. */
  async chooseLibrary(group: 'Sort by' | 'Progress', choice: string): Promise<void> {
    const button = this.page.getByRole('group', { name: group }).getByRole('button', { name: choice, exact: true });
    await button.click();
    await expect(button).toHaveAttribute('aria-pressed', 'true');
  }

  async selectedLibraryChoices(): Promise<string[]> {
    return (await this.page.getByRole('button', { pressed: true }).allInnerTexts()).map((text) => text.trim());
  }

  /** The titles of the library grid, in order. */
  async libraryTitles(): Promise<string[]> {
    return this.page.getByTestId('library-item').getByRole('link').allInnerTexts();
  }

  libraryItem(title: string): Locator {
    return this.page.getByTestId('library-item').filter({ hasText: title });
  }

  /** Open the app on the watch list, as when coming back to it. */
  async openWatchList(): Promise<void> {
    await this.page.goto('/episodes/watch-list');
    await expect(this.watchList()).toBeVisible();
  }

  async openUpcoming(): Promise<void> {
    await this.openTab('Episodes');
    await this.episodesTabs().getByRole('link', { name: 'Upcoming' }).click();
  }

  episodesTabs(): Locator {
    return this.page.getByRole('navigation', { name: 'Episodes' });
  }

  watchList(): Locator {
    return this.page.getByTestId('watch-list');
  }

  /** A section of the watch list by its title, such as "Watch next". */
  watchListSection(name: string): Locator {
    return this.watchList().getByRole('region', { name });
  }

  /** The watch list's card of a show. */
  card(show: string): Locator {
    return this.watchList()
      .getByTestId('episode')
      .filter({ has: this.page.getByRole('link', { name: show }) });
  }

  /** The episode a list card shows, such as "S01 | E02+3". */
  async cardEpisode(show: string): Promise<string> {
    return (await this.card(show).getByTestId('episode-code').innerText()).replace(/\s+/g, '');
  }

  async checkCard(show: string): Promise<void> {
    await this.card(show)
      .getByRole('button', { name: new RegExp(`^Mark .* of ${show} watched$`) })
      .click();
  }

  /** Swipe a card left with a finger, or open its menu with a mouse or keyboard, then pick an action. */
  async cardAction(show: string, action: string, how: 'swipe' | 'menu'): Promise<void> {
    if (how === 'menu') {
      await this.card(show)
        .getByRole('button', { name: `More for ${show}` })
        .click();
      await this.page.getByRole('menuitem', { name: action }).click();
      return;
    }
    const box = (await this.card(show).boundingBox())!;
    const y = box.y + box.height / 2;
    await this.touchDrag({ x: box.x + box.width - 40, y }, { x: box.x + 40, y });
    await this.card(show).getByRole('button', { name: action }).click();
  }

  viewToggle(): Locator {
    return this.page.getByTestId('view-toggle');
  }

  /** Whether the watch list shows posters in a grid rather than rows. */
  async isGrid(): Promise<boolean> {
    return (await this.watchList().locator('.card-grid').count()) > 0;
  }

  history(): Locator {
    return this.page.getByTestId('history');
  }

  historyEntries(): Locator {
    return this.history().getByTestId('history-entry');
  }

  /** At the top of the content, scroll further up: a wheel on desktop, a finger pulling down on a phone. */
  async scrollUpFromTop(touch: boolean): Promise<void> {
    await this.content().evaluate((element) => (element.scrollTop = 0));
    const box = (await this.content().boundingBox())!;
    const x = box.x + box.width / 2;
    // Just past the pull that loads it: what the finger pulls further scrolls into the history.
    if (touch) await this.touchDrag({ x, y: box.y + 150 }, { x, y: box.y + 200 });
    else {
      await this.page.mouse.move(x, box.y + 150);
      await this.page.mouse.wheel(0, -400);
    }
  }

  /** Scroll the content back to its top, as when reading further up the history. */
  async scrollToTop(): Promise<void> {
    await this.content().evaluate((element) => element.scrollTo({ top: 0 }));
  }

  /** The shell's content area, the only element that scrolls. */
  content(): Locator {
    return this.page.getByRole('main');
  }

  navigation(): Locator {
    return this.page.getByRole('navigation', { name: 'Main navigation' });
  }

  async back(): Promise<void> {
    await this.page.goBack();
  }

  /** A real touch drag, through the browser's input layer, in steps like a finger. */
  private async touchDrag(from: { x: number; y: number }, to: { x: number; y: number }): Promise<void> {
    const session = await this.page.context().newCDPSession(this.page);
    const point = (x: number, y: number) => [{ x: Math.round(x), y: Math.round(y) }];
    await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: point(from.x, from.y) });
    const steps = 8;
    for (let step = 1; step <= steps; step++) {
      const x = from.x + ((to.x - from.x) * step) / steps;
      const y = from.y + ((to.y - from.y) * step) / steps;
      await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: point(x, y) });
    }
    // The finger rests before lifting, so the page does not fling on.
    await this.page.waitForTimeout(150);
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await session.detach();
  }
}
