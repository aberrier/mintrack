import { expect, Locator } from '@playwright/test';
import { Viewer } from './fixtures';

/** A title no other test uses: the fake TMDB serves one show and one movie per searched title. */
export function uniqueTitle(base: string, options: { ended?: boolean } = {}): string {
  const title = `${base} ${Math.random().toString(36).slice(2, 8)}`;
  return options.ended ? `Ended ${title}` : title;
}

export async function openShow(viewer: Viewer, title: string): Promise<void> {
  await viewer.app.search(title);
  await viewer.app.openResult(title);
}

export async function openMovie(viewer: Viewer, title: string): Promise<void> {
  await viewer.app.search(title, 'Movies');
  await viewer.app.openResult(title);
}

/** Add the open show to the library and return its status. */
export async function addShow(viewer: Viewer): Promise<string> {
  await viewer.app.clickButton('Add to library');
  return showStatus(viewer);
}

export async function showStatus(viewer: Viewer): Promise<string> {
  await expect(viewer.app.status('show-status')).toBeVisible();
  return (await viewer.app.status('show-status').innerText()).trim();
}

/** Tap an episode of the open show: marks it, or unmarks it when watched. */
export async function tapEpisode(viewer: Viewer, season: number, episode: number): Promise<void> {
  await viewer.app.toggleEpisode(season, episode);
}

export async function isWatched(viewer: Viewer, season: number, episode: number): Promise<boolean> {
  await viewer.app.openSeason(season);
  return (await viewer.app.episode(season, episode).getAttribute('aria-pressed')) === 'true';
}

/** Accept the offer to mark the earlier episodes and return what it said. */
export async function acceptEarlierEpisodes(viewer: Viewer): Promise<string> {
  return viewer.app.acceptPreviousOffer();
}

/**
 * One tap on a season's check; returns its `watched/aired` right after, before the server answers. Then waits until
 * the show the page loads again once the server saved the marks is on screen: the Watch next card it may bring moves
 * the seasons down, under a next tap.
 */
export async function tapSeason(viewer: Viewer, season: number): Promise<string> {
  const reloaded = viewer.app.nextShowLoad();
  await viewer.app.seasonCheck(season).click();
  await viewer.app.rendered();
  const progress = await viewer.app.seasonProgress(season);
  await reloaded;
  await viewer.app.rendered();
  return progress;
}

/** One tap on a fully watched season's check; returns the question it asks before unmarking. */
export async function tapWatchedSeason(viewer: Viewer, season: number): Promise<string> {
  await viewer.app.seasonCheck(season).click();
  return viewer.app.dialogQuestion();
}

/** The show page's Watch next card, such as "S01|E02+3". */
export async function watchNext(viewer: Viewer): Promise<string> {
  return viewer.app.watchNextEpisode();
}

export async function checkWatchNext(viewer: Viewer): Promise<void> {
  await viewer.app.checkWatchNext();
}

export async function seasonProgress(viewer: Viewer, season: number): Promise<string> {
  return viewer.app.seasonProgress(season);
}

export async function isSeasonWatched(viewer: Viewer, season: number): Promise<boolean> {
  return (await viewer.app.seasonCheck(season).getAttribute('aria-pressed')) === 'true';
}

/** Answer the question a tap on a fully watched season asks. */
export async function answerUnmark(viewer: Viewer, answer: 'Unmark' | 'Cancel'): Promise<void> {
  await viewer.app.answerDialog(answer);
}

/** Whether confetti fell over the screen once the server saved what `tap` marked. */
export async function confettiAfter(viewer: Viewer, tap: () => Promise<unknown>): Promise<boolean> {
  return viewer.app.confettiAfter(tap);
}

/** Whether the title's poster carries the Finished badge, in the Profile tab's row. */
export async function finishedBadgeOnProfile(viewer: Viewer, title: string): Promise<boolean> {
  await viewer.app.openTab('Profile');
  const item = viewer.app.profileItem('Shows', title);
  await expect(item).toBeVisible();
  return shown(viewer.app.finishedBadge(item));
}

/** The header's facts under the title, such as "1h 58m · 1 May 2020". */
export async function headerFacts(viewer: Viewer): Promise<string> {
  return (await viewer.app.mediaFacts().innerText()).trim();
}

/** Tap the movie's check; returns the line saying when it was watched, as the screen shows it at once. */
export async function tapMovieCheck(viewer: Viewer): Promise<string> {
  const check = viewer.app.movieCheck();
  const pressed = await check.getAttribute('aria-pressed');
  await check.click();
  await expect(check).toHaveAttribute('aria-pressed', pressed === 'true' ? 'false' : 'true');
  return (await viewer.app.movieWatched().innerText()).trim();
}

/** Today as the app writes a date of this year in the user's time zone, such as "18 Nov". */
export async function today(viewer: Viewer): Promise<string> {
  const timeZone = await viewer.api.timeZone();
  return new Intl.DateTimeFormat('en-GB', { month: 'short', day: 'numeric', timeZone }).format(new Date());
}

export async function movieStatus(viewer: Viewer): Promise<string> {
  return (await viewer.app.status('movie-status').innerText()).trim();
}

export async function markMovieWatched(viewer: Viewer): Promise<string> {
  await viewer.app.movieCheck().click();
  await expect(viewer.app.status('movie-status')).toHaveText('Watched');
  return (await viewer.app.status('movie-status').innerText()).trim();
}

/** A title's library card without its title: progress and status, such as "0/5 · Watch later". */
export async function libraryEntry(viewer: Viewer, type: 'Shows' | 'Movies', title: string): Promise<string> {
  await viewer.app.openLibrary(type);
  await expect(viewer.app.libraryItem(title)).toBeVisible();
  return viewer.app.libraryItemDetail(title);
}

/** Add shows to the library through the API, for a given state the scenario does not exercise. */
export async function seedShows(viewer: Viewer, titles: string[]): Promise<void> {
  for (const title of titles) {
    const tmdbId = await viewer.api.findShow(title);
    expect((await viewer.api.loadShow(tmdbId)).ok(), `Loading show "${title}"`).toBe(true);
    expect((await viewer.api.addShow(tmdbId)).ok(), `Adding show "${title}"`).toBe(true);
  }
}

/**
 * Scroll the library down to the card of `title`, open it and come back. Returns how far the list was scrolled, and
 * whether the card is on screen again.
 */
export async function openAndComeBack(
  viewer: Viewer,
  title: string,
): Promise<{ scrolled: number; cardOnScreen: boolean }> {
  const item = viewer.app.libraryItem(title);
  await item.scrollIntoViewIfNeeded();
  const scrolled = await viewer.app.content().evaluate((element) => element.scrollTop);
  await viewer.app.openLibraryItem(title);
  await viewer.app.back();
  // Other tests share the library and may add cards above it meanwhile: the card is checked on screen, not the pixel.
  return { scrolled, cardOnScreen: await inViewport(item) };
}

/** Whether the element shows, waiting for it as an expectation does. */
export function shown(locator: Locator): Promise<boolean> {
  return expect(locator)
    .toBeVisible()
    .then(
      () => true,
      () => false,
    );
}

function inViewport(locator: Locator): Promise<boolean> {
  return expect(locator)
    .toBeInViewport()
    .then(
      () => true,
      () => false,
    );
}
