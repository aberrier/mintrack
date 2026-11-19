import { expect, Locator, Page } from '@playwright/test';

export type Tab = 'Episodes' | 'Discover' | 'Profile' | 'Admin';

/** A vibration the app asked for, and whether the tap that caused it was still being handled. */
export interface RecordedVibration {
  pattern: VibratePattern;
  duringTap: boolean;
}

/** MinTrack's pages as a user reaches them: bottom navigation, links, buttons. Locators live only here. */
export class AppDriver {
  constructor(private readonly page: Page) {}

  /** Wait for the app to render what the last tap changed: Angular renders on the next frame, not during the tap. */
  async rendered(): Promise<void> {
    await this.page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve))));
  }

  async open(): Promise<void> {
    await this.page.goto('/');
    await expect(this.navigation()).toBeVisible();
  }

  /** Open an address typed in or bookmarked. */
  async openAddress(address: string): Promise<void> {
    await this.page.goto(address);
  }

  /** The address the app shows: path and query. */
  address(): string {
    const url = new URL(this.page.url());
    return url.pathname + url.search;
  }

  /** The browser tab's title. */
  title(): Promise<string> {
    return this.page.title();
  }

  /** True when nothing overflows the viewport horizontally. */
  fitsWidth(): Promise<boolean> {
    return this.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  }

  /** Whether the device has a touch screen, as a phone does. */
  isTouch(): Promise<boolean> {
    return this.page.evaluate(() => navigator.maxTouchPoints > 0);
  }

  /** The bottom navigation's tabs, in order. */
  tabLinks(): Locator {
    return this.navigation().getByRole('link');
  }

  /** The tab of the open screen. */
  activeTab(): Locator {
    return this.navigation().locator('[aria-current="page"]');
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
      .locator('h2, h3, h4, h5, mat-label, button, a[href]')
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

  /** Every API request fails, as when the server cannot be reached. */
  async cutOffApi(): Promise<void> {
    await this.page.route('/api/**', (route) => route.abort());
  }

  /** The message the app shows instead of a page when the server cannot be reached. */
  unreachable(): Locator {
    return this.page.getByTestId('unreachable');
  }

  /** The upcoming episodes the server sends, replaced by `response`. */
  async serveUpcoming(response: object): Promise<void> {
    await this.page.route('/api/upcoming', (route) => route.fulfill({ json: response }));
  }

  /** The watch list the server sends, replaced by `response`. */
  async serveWatchList(response: object): Promise<void> {
    await this.page.route('/api/watch-list', (route) => route.fulfill({ json: response }));
  }

  /** The CSS animations and transitions of the page still in effect, finished ones that hold their end state included. */
  animationsInEffect(): Promise<number> {
    return this.page.evaluate(() => document.getAnimations().length);
  }

  /** Answer the server's error for requests whose URL ends with `suffix`. */
  async failRequests(suffix: string): Promise<void> {
    await this.page.route(
      (url) => url.pathname.endsWith(suffix),
      (route) => route.fulfill({ status: 500, body: 'down' }),
    );
  }

  /** Upcoming's days, each a region named after its day: Today, Tomorrow, a weekday or a date. */
  upcomingDays(): Locator {
    return this.page.getByTestId('day');
  }

  upcomingDay(name: string): Locator {
    return this.page.getByRole('region', { name, exact: true });
  }

  /** Upcoming's month names, where a new month starts. */
  upcomingMonths(): Locator {
    return this.page.getByTestId('month');
  }

  /** The Admin tab's users. */
  adminUsers(): Locator {
    return this.page.getByTestId('users').getByRole('listitem');
  }

  /** The next response to a request whose URL ends with `suffix`. */
  nextResponse(suffix: string): Promise<unknown> {
    return this.page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(suffix));
  }

  /** The next answer to loading a show, as the show page does again once the writes to the show are saved. */
  nextShowLoad(): Promise<unknown> {
    return this.page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' && /^\/api\/shows\/\d+$/.test(new URL(response.url()).pathname),
    );
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

  trendingItems(name: string): Locator {
    return this.trendingRow(name).getByTestId('trending-item');
  }

  /** The titles of a trending row, once it has loaded. */
  async trendingTitles(name: string): Promise<string[]> {
    await expect(this.trendingItems(name).first()).toBeVisible();
    return trimmed(await this.trendingItems(name).getByRole('link').allInnerTexts());
  }

  /** The pages a trending row's posters link to, once it has loaded. */
  async trendingLinks(name: string): Promise<string[]> {
    await expect(this.trendingItems(name).first()).toBeVisible();
    return this.trendingItems(name)
      .getByRole('link')
      .evaluateAll((links) => links.map((link) => link.getAttribute('href') ?? ''));
  }

  /** Empty Discover's search field, as with the field's clear button or the keyboard. */
  async clearSearch(): Promise<void> {
    await this.page.getByRole('searchbox', { name: 'Search shows and movies' }).fill('');
  }

  async searchResultTitles(): Promise<string[]> {
    return trimmed(await this.searchResults().getByRole('link').allInnerTexts());
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

  /** The movie page's line giving its first digital release, when known. */
  movieDigitalRelease(): Locator {
    return this.page.getByTestId('movie-digital-release');
  }

  movieCheck(): Locator {
    return this.page.getByRole('button', { name: 'Mark watched', exact: true });
  }

  /** Open one of the show page's tabs, About and Episodes, once its content is on screen. */
  async openShowTab(name: 'About' | 'Episodes'): Promise<void> {
    const link = this.page.getByRole('navigation', { name: 'Show sections' }).getByRole('link', { name });
    await link.click();
    await expect(link).toHaveAttribute('aria-current', 'page');
    await this.rendered();
  }

  /** The show page's text, where the About tab lists facts such as the network. */
  showText(text: string): Locator {
    return this.content().getByText(text).last();
  }

  watchNext(): Locator {
    return this.page.getByTestId('watch-next');
  }

  /** The episode the show page's Watch next card offers, such as "S01|E02+3". */
  async watchNextEpisode(): Promise<string> {
    return compact(await this.watchNext().getByTestId('episode-code').innerText());
  }

  async checkWatchNext(): Promise<void> {
    await this.watchNext()
      .getByRole('button', { name: /^Mark .* watched$/ })
      .click();
    await this.rendered();
  }

  /** Season 0 holds the specials. */
  private seasonTitle(season: number): string {
    return season === 0 ? 'Specials' : `Season ${season}`;
  }

  seasonToggle(season: number): Locator {
    return this.page.getByRole('button', { name: new RegExp(`^${this.seasonTitle(season)} \\d+/\\d+$`) });
  }

  /** A season's check: marks its aired episodes, or asks to unmark it once all are watched. */
  seasonCheck(season: number): Locator {
    return this.page.getByRole('button', { name: `Mark ${this.seasonTitle(season)} watched`, exact: true });
  }

  /** A season row's `watched/aired`. */
  async seasonProgress(season: number): Promise<string> {
    return (await this.seasonToggle(season).getByTestId('season-progress').innerText()).trim();
  }

  /**
   * The open confirmation dialog's question. While it is open, the page behind it is hidden from the accessibility
   * tree, so role locators no longer find that page's buttons.
   */
  async dialogQuestion(): Promise<string> {
    const title = this.page.getByRole('dialog').getByRole('heading');
    await expect(title).toBeVisible();
    return (await title.innerText()).trim();
  }

  /** Answer the open confirmation dialog with one of its buttons, once the page behind it shows the answer. */
  async answerDialog(button: string): Promise<void> {
    await this.page.getByRole('dialog').getByRole('button', { name: button }).click();
    await expect(this.page.getByRole('dialog')).toHaveCount(0);
    await this.rendered();
  }

  confetti(): Locator {
    return this.page.getByTestId('confetti');
  }

  /**
   * Run `write`, which marks episodes and returns once the page handled the server's answer; returns whether confetti
   * fell. The confetti canvas is on the page from the launch until the last confetti fell, seconds later.
   */
  async confettiAfter(write: () => Promise<unknown>): Promise<boolean> {
    await write();
    return (await this.confetti().count()) > 0;
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

  /**
   * The snackbar on screen, not the one it replaced, which leaves meanwhile: Material marks a leaving one with the
   * mat-exit attribute at once, and with its exit class only at the next render.
   */
  snackBar(): Locator {
    return this.page.locator('mat-snack-bar-container:not([mat-exit])');
  }

  /** The snackbar's action, such as Undo. */
  async snackBarAction(name: string): Promise<void> {
    await this.snackBar().getByRole('button', { name }).click();
  }

  /** Whether this is a touch screen whose browser has the Vibration API, as Android's does and iOS's does not. */
  canVibrate(): Promise<boolean> {
    return this.page.evaluate(() => typeof navigator.vibrate === 'function' && matchMedia('(pointer: coarse)').matches);
  }

  /**
   * Load the app again, its vibrations recorded instead of felt, each with whether the tap that asked for it was
   * still being handled (the page's transient user activation).
   */
  async recordVibrations(): Promise<void> {
    await this.page.addInitScript(() => {
      if (typeof navigator.vibrate !== 'function') return;
      const recorded: RecordedVibration[] = [];
      Object.assign(window, { recordedVibrations: recorded });
      navigator.vibrate = (pattern) =>
        recorded.push({ pattern: pattern as VibratePattern, duringTap: navigator.userActivation.isActive }) > 0;
    });
    await this.reload();
  }

  /** The vibrations since the app loaded or since last taken, oldest first; the record starts empty again. */
  takeVibrations(): Promise<RecordedVibration[]> {
    return this.page.evaluate(
      () => (window as unknown as { recordedVibrations?: RecordedVibration[] }).recordedVibrations?.splice(0) ?? [],
    );
  }

  vibrationSwitch(): Locator {
    return this.page.getByRole('switch', { name: 'Vibrate on taps' });
  }

  /** The show page's Watch next place while the server has not said which episode it holds. */
  watchNextPending(): Locator {
    return this.page.getByTestId('watch-next-pending');
  }

  /** How far down the screen the show page's list of seasons starts. */
  async seasonsTop(): Promise<number> {
    return (await this.page.getByRole('heading', { name: 'All episodes' }).boundingBox())!.y;
  }

  /** The open show's or movie's TMDB id, from the address. */
  mediaId(): string {
    return new URL(this.page.url()).pathname.split('/').at(-1)!;
  }

  /** The Profile tab's row of shows, movies or shows to watch later. */
  profileRow(type: 'Shows' | 'Movies' | 'Watch later'): Locator {
    return this.page.getByRole('region', { name: type, exact: true });
  }

  profileItem(type: 'Shows' | 'Movies' | 'Watch later', title: string): Locator {
    return this.profileRow(type).getByTestId('profile-item').filter({ hasText: title });
  }

  /** The titles of a row of the Profile tab, once it has loaded. */
  async profileTitles(type: 'Shows' | 'Movies' | 'Watch later'): Promise<string[]> {
    const items = this.profileRow(type).getByTestId('profile-item');
    await expect(items.first()).toBeVisible();
    return trimmed(await items.getByRole('link').allInnerTexts());
  }

  /** The Profile tab's gear, opening the settings. */
  settingsLink(): Locator {
    return this.page.getByRole('link', { name: 'Settings', exact: true });
  }

  /** Wait for the settings loaded from the server: the import card and the device list. */
  async settingsLoaded(): Promise<void> {
    await expect(this.page.getByRole('button', { name: 'Choose a file and import' })).toBeVisible();
    await expect(this.page.getByTestId('device').getByText('This device', { exact: true })).toBeVisible();
  }

  logOutButtons(): Locator {
    return this.page.getByRole('button', { name: /^Log out/ });
  }

  async openSettings(): Promise<void> {
    await this.openTab('Profile');
    await this.settingsLink().click();
    await expect(this.heading()).toHaveText('Settings');
  }

  /** The page explaining how to connect an assistant, from Learn more in the API tokens settings. */
  async openMcpHelp(): Promise<void> {
    await this.openSettings();
    await this.page.getByRole('region', { name: 'API tokens' }).getByRole('link', { name: 'Learn more' }).click();
    await expect(this.heading()).toHaveText('Connect an AI assistant');
  }

  /** The notifications guide, from its link in the Notifications settings. */
  async openPushHelp(): Promise<void> {
    await this.openSettings();
    await this.page.getByTestId('push-settings').getByRole('link', { name: 'How to get notifications' }).click();
    await expect(this.heading()).toHaveText('Get notifications');
  }

  /** The notifications guide's sections, in order: Android's and iPhone's, then the others. */
  async pushHelpSections(): Promise<string[]> {
    return (await this.page.getByRole('heading', { level: 2 }).allInnerTexts()).map((text) => text.trim());
  }

  /** The Statistics page, from its button on the Profile tab. */
  async openStats(): Promise<void> {
    await this.openTab('Profile');
    await this.page.getByRole('link', { name: 'Statistics', exact: true }).click();
    await expect(this.heading()).toHaveText('Statistics');
  }

  /**
   * What the loaded Statistics page shows: time spent, totals and streaks by label, months, top genres and networks;
   * null for its empty state.
   */
  async stats(): Promise<{
    time: string;
    figures: Record<string, string>;
    months: string[];
    genres: string[];
    networks: string[];
  } | null> {
    const time = this.page.getByTestId('stats-total-time');
    const empty = this.page.getByText('Nothing watched yet');
    await expect(time.or(empty)).toBeVisible();
    if (await empty.isVisible()) return null;
    const figures: Record<string, string> = {};
    for (const figure of await this.page.getByTestId('stats-figure').all()) {
      figures[(await figure.locator('dt').innerText()).trim()] = (await figure.locator('dd').innerText()).trim();
    }
    const names = async (ranking: string) =>
      trimmed(await this.page.getByTestId(ranking).getByTestId('stats-ranked-name').allInnerTexts());
    return {
      time: (await time.innerText()).trim(),
      figures,
      months: await this.page
        .getByTestId('stats-months')
        .getByRole('listitem')
        .evaluateAll((items) => items.map((item) => item.getAttribute('aria-label') ?? '')),
      genres: await names('stats-genres'),
      networks: await names('stats-networks'),
    };
  }

  /** A code sample of the MCP help page: the server address, the JSON configuration or the Claude Code command. */
  async mcpSample(sample: 'url' | 'json' | 'command'): Promise<string> {
    return (await this.page.getByTestId(`mcp-${sample}`).innerText()).trim();
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

  librarySearch(): Locator {
    return this.page.getByLabel('Search by title');
  }

  async searchLibrary(text: string): Promise<void> {
    await this.librarySearch().fill(text);
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

  /** A library card's line under its title: progress and status, such as "0/5 · Watch later". */
  async libraryItemDetail(title: string): Promise<string> {
    return (await this.libraryItem(title).getByTestId('tile-detail').innerText()).replace(/\s+/g, ' ').trim();
  }

  async openLibraryItem(title: string): Promise<void> {
    await this.libraryItem(title).getByRole('link').click();
    await expect(this.status('show-status')).toBeVisible();
  }

  /** Open the app on the watch list, as when coming back to it. */
  async openWatchList(): Promise<void> {
    await this.page.goto('/episodes/watch-list');
    await expect(this.watchList()).toBeVisible();
  }

  /** Load the watch list again, as when coming back later, and wait until the server's list is on screen. */
  async reloadWatchList(): Promise<void> {
    const loaded = this.nextResponse('/api/watch-list');
    await this.page.reload();
    await loaded;
    await expect(this.watchList()).toBeVisible();
    await this.rendered();
  }

  async openUpcoming(): Promise<void> {
    await this.openTab('Episodes');
    await this.episodesTabs().getByRole('link', { name: 'Upcoming' }).click();
  }

  episodesTabs(): Locator {
    return this.page.getByRole('navigation', { name: 'Episodes' });
  }

  episodesTab(name: 'Watch list' | 'Upcoming'): Locator {
    return this.episodesTabs().getByRole('link', { name });
  }

  /** What a list says when it has nothing to show. */
  emptyState(): Locator {
    return this.page.getByTestId('empty');
  }

  /** The welcome of an empty watch list, with its steps. */
  welcome(): Locator {
    return this.page.getByTestId('welcome');
  }

  /** The titles of the welcome's steps, in order. */
  async welcomeSteps(): Promise<string[]> {
    await expect(this.welcome()).toBeVisible();
    return (await this.welcome().getByRole('heading', { level: 3 }).allInnerTexts()).map((text) => text.trim());
  }

  async followWelcomeLink(name: string): Promise<void> {
    await this.welcome().getByRole('link', { name }).click();
  }

  async hideWelcome(): Promise<void> {
    await this.welcome().getByRole('button', { name: 'Hide these steps' }).click();
  }

  /** A Settings group's title, such as Integrations. */
  settingsGroupTitle(name: string): Locator {
    return this.page.getByRole('heading', { level: 2, name, exact: true });
  }

  /** An upcoming episode's line under its title: its air time. */
  upcomingEpisodeDetail(day: Locator): Locator {
    return day.getByTestId('episode-detail');
  }

  upcomingEpisode(day: Locator, name: string): Locator {
    return day.getByRole('button', { name });
  }

  watchList(): Locator {
    return this.page.getByTestId('watch-list');
  }

  /** A section of the watch list by its title, such as "Watch next". */
  watchListSection(name: string): Locator {
    return this.watchList().getByRole('region', { name });
  }

  /** The watch list's cards, top first. */
  cards(): Locator {
    return this.watchList().getByTestId('episode');
  }

  /** The title of the watch list section holding the show's card, such as "Watch next". */
  async cardSection(show: string): Promise<string> {
    await expect(this.card(show)).toBeVisible();
    return this.card(show).evaluate((card) => {
      const labelledBy = card.closest('section')?.getAttribute('aria-labelledby');
      return (labelledBy && document.getElementById(labelledBy)?.textContent?.trim()) || '';
    });
  }

  /** The watch list's card of a show. */
  card(show: string): Locator {
    return this.watchList()
      .getByTestId('episode')
      .filter({ has: this.page.getByRole('link', { name: show }).or(this.page.getByLabel(show)) });
  }

  /** The episode a list card shows, such as "S01 | E02+3". */
  async cardEpisode(show: string): Promise<string> {
    return compact(await this.card(show).getByTestId('episode-code').innerText());
  }

  /** The check of a show's card. */
  cardCheck(show: string): Locator {
    return this.card(show).getByRole('button', { name: new RegExp(`^Mark .* of ${show} watched$`) });
  }

  async checkCard(show: string): Promise<void> {
    await this.cardCheck(show).click();
  }

  /** The watch list's section headings, each a button folding its section. */
  sectionToggles(): Locator {
    return this.watchList().locator('h2 > button[aria-expanded]');
  }

  sectionToggle(name: string): Locator {
    return this.sectionToggles().filter({ hasText: name });
  }

  /**
   * Reach a card's menu with the keyboard only (Tab from its episode), open it with Enter, move to the action with the
   * arrow keys and pick it with Enter. Returns whether a focus ring showed around the menu button while focused.
   */
  async cardActionByKeyboard(show: string, action: string): Promise<boolean> {
    await this.card(show).locator('button.open').focus();
    await this.page.keyboard.press('Tab');
    const menuButton = this.card(show).getByRole('button', { name: `More for ${show}` });
    await expect(menuButton).toBeFocused();
    const ring = await menuButton.evaluate((button) => {
      const indicator = button.querySelector('.mat-focus-indicator') ?? button;
      const style = getComputedStyle(indicator, '::before');
      return style.display !== 'none' && style.content !== 'none' && parseFloat(style.borderTopWidth) > 0;
    });
    await this.page.keyboard.press('Enter');
    const item = this.page.getByRole('menuitem', { name: action });
    await expect(this.page.getByRole('menuitem').first()).toBeFocused();
    for (let step = 0; step < 5 && !(await item.evaluate((element) => element === document.activeElement)); step++)
      await this.page.keyboard.press('ArrowDown');
    await expect(item).toBeFocused();
    await this.page.keyboard.press('Enter');
    return ring;
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

  /** Switch the screen's list between rows and a grid. */
  async toggleView(): Promise<void> {
    await this.viewToggle().click();
    await this.rendered();
  }

  history(): Locator {
    return this.page.getByTestId('history');
  }

  /** The mark at the top of the history once its oldest entry has loaded. */
  historyStart(): Locator {
    return this.history().getByTestId('history-start');
  }

  historyEntries(): Locator {
    return this.history().getByTestId('history-entry');
  }

  historyEntry(title: string): Locator {
    return this.historyEntries().filter({ hasText: title });
  }

  /** At the top of the content, scroll further up: a wheel on desktop, a finger pulling down on a phone. */
  async scrollUpFromTop(touch: boolean): Promise<void> {
    await this.content().evaluate((element) => (element.scrollTop = 0));
    const box = (await this.content().boundingBox())!;
    const x = box.x + box.width / 2;
    // Just past the pull that loads it: what the finger pulls further scrolls into the history.
    if (touch) await this.touchDrag({ x, y: box.y + 150 }, { x, y: box.y + 200 });
    else if (this.page.context().browser()?.browserType().name() === 'webkit') {
      // Playwright drives neither a finger's drag nor a wheel in mobile WebKit: the page gets the wheel's event.
      await this.content().dispatchEvent('wheel', { deltaY: -400 });
    } else {
      await this.page.mouse.move(x, box.y + 150);
      await this.page.mouse.wheel(0, -400);
    }
  }

  /** Scroll the content back to its top, as when reading further up the history. */
  async scrollToTop(): Promise<void> {
    await this.content().evaluate((element) => element.scrollTo({ top: 0 }));
  }

  /** Open an episode's sheet from its row on the show page. */
  async openEpisodeSheet(season: number, episode: number): Promise<void> {
    await this.openSeason(season);
    await this.page
      .getByTestId('episode-open')
      .filter({ hasText: new RegExp(`^\\s*${episode}\\.`) })
      .first()
      .click();
    await expect(this.episodeSheet().getByTestId('sheet-title')).toBeVisible();
  }

  /** Open the sheet of a card's episode, such as one of the watch list's. */
  async openCardSheet(card: Locator): Promise<void> {
    await card.locator('button.open, button.open-tile').click();
    await expect(this.episodeSheet().getByTestId('sheet-title')).toBeVisible();
  }

  episodeSheet(): Locator {
    return this.page.locator('mat-bottom-sheet-container');
  }

  async closeEpisodeSheet(): Promise<void> {
    await this.page.keyboard.press('Escape');
    await expect(this.episodeSheet()).toHaveCount(0);
  }

  /** The sheet's or the page's line by its test id, such as `sheet-watched` or `tmdb-score`. */
  async textOf(testId: string): Promise<string> {
    const element = this.page.getByTestId(testId);
    await expect(element).toBeVisible();
    return (await element.innerText()).replace(/\s+/g, ' ').trim();
  }

  /** The show's or the movie's line giving TMDB's score. */
  tmdbScoreLine(): Locator {
    return this.page.getByTestId('tmdb-score');
  }

  /** The sheet's check, marking or unmarking its episode. */
  sheetCheck(): Locator {
    return this.episodeSheet().getByRole('button', { name: 'Mark watched', exact: true });
  }

  /** Type a watch date and time into the sheet, as its picker would set it. */
  async setWatchDate(local: string): Promise<void> {
    await this.episodeSheet().getByLabel('Watched on').fill(local);
  }

  /** The watch date and time the sheet's field shows, as "2025-03-14T20:30". */
  watchDateShown(): Promise<string> {
    return this.episodeSheet().getByLabel('Watched on').inputValue();
  }

  /** The rating form of the sheet, or else of the page. */
  private ratingForm(): Locator {
    return this.page.locator('app-rating-form').last();
  }

  /** Pick stars, write a review and save; waits for the server's answer. */
  async rate(stars: number, review: string): Promise<void> {
    const form = this.ratingForm();
    await form.getByRole('button', { name: `${stars} out of 5`, exact: true }).click();
    await form.getByLabel('Review').fill(review);
    const saved = this.nextResponse('/rating');
    await form.getByRole('button', { name: 'Save', exact: true }).click();
    await saved;
  }

  async removeRating(): Promise<void> {
    const removed = this.nextResponse('/rating');
    await this.ratingForm().getByRole('button', { name: 'Remove', exact: true }).click();
    await removed;
  }

  async pickStars(stars: number): Promise<void> {
    await this.ratingForm()
      .getByRole('button', { name: `${stars} out of 5`, exact: true })
      .click();
  }

  /**
   * Tap the rating form's button where the screen shows it, as a finger would, without scrolling it into view first:
   * whatever lies on top there gets the tap. Taps once the button is enabled, as a finger would wait for it after
   * picking stars. Returns the rating request it sent, and the stars it saves.
   */
  async tapRatingButton(name: 'Save' | 'Remove'): Promise<{ method: string; stars: number | null }> {
    const button = this.ratingForm().getByRole('button', { name, exact: true });
    await expect(button).toBeEnabled();
    const box = (await button.boundingBox())!;
    const sent = this.page.waitForRequest((request) => new URL(request.url()).pathname.endsWith('/rating'));
    const answered = this.nextResponse('/rating');
    await this.page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    const request = await sent;
    await answered;
    return { method: request.method(), stars: request.postDataJSON()?.stars ?? null };
  }

  /** The snackbar's text once it shows, and whether the episode sheet ends above it. */
  async snackBarOverSheet(): Promise<{ message: string; sheetAbove: boolean }> {
    const snackBar = this.snackBar();
    await expect(snackBar).toBeVisible();
    // Measured once it has grown to its full size.
    await snackBar.evaluate((bar) => Promise.all(bar.getAnimations({ subtree: true }).map((each) => each.finished)));
    const message = (await snackBar.locator('[matsnackbarlabel]').innerText()).trim();
    const sheet = (await this.page.locator('.mat-bottom-sheet-container').boundingBox())!;
    const bar = (await snackBar.boundingBox())!;
    return { message, sheetAbove: sheet.y + sheet.height <= bar.y };
  }

  /** The stars picked in the rating form (0 for none) and its review. */
  async ratingShown(): Promise<{ stars: number; review: string }> {
    const form = this.ratingForm();
    await expect(form).toBeVisible();
    const pressed = await form
      .locator('button[aria-pressed="true"]')
      .evaluateAll((buttons) => buttons.map((button) => button.getAttribute('aria-label')));
    return {
      stars: pressed.length ? Number(pressed[0]!.split(' ')[0]) : 0,
      review: await form.getByLabel('Review').inputValue(),
    };
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

  /**
   * A real touch drag, through the browser's input layer, in steps 16 ms apart like a finger. The events carry their
   * own times: the finger rests 150 ms before lifting, so the page does not fling on, and the test does not wait.
   */
  private async touchDrag(from: { x: number; y: number }, to: { x: number; y: number }): Promise<void> {
    const session = await this.page.context().newCDPSession(this.page);
    const point = (x: number, y: number) => [{ x: Math.round(x), y: Math.round(y) }];
    const start = Date.now() / 1000;
    const touch = (type: 'touchStart' | 'touchMove' | 'touchEnd', at: number, x = to.x, y = to.y) =>
      session.send('Input.dispatchTouchEvent', {
        type,
        touchPoints: type === 'touchEnd' ? [] : point(x, y),
        timestamp: start + at,
      });
    const steps = 8;
    await touch('touchStart', 0, from.x, from.y);
    for (let step = 1; step <= steps; step++) {
      await touch(
        'touchMove',
        step * 0.016,
        from.x + ((to.x - from.x) * step) / steps,
        from.y + ((to.y - from.y) * step) / steps,
      );
    }
    const rest = steps * 0.016 + 0.15;
    await touch('touchMove', rest);
    await touch('touchEnd', rest + 0.01);
    await session.detach();
  }
}

function trimmed(texts: string[]): string[] {
  return texts.map((text) => text.trim());
}

/** Text without its spaces, as an episode code reads: "S01|E02+3". */
function compact(text: string): string {
  return text.replace(/\s+/g, '');
}
