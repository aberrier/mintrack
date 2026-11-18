import { expect } from '@playwright/test';
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

/** One tap on a season's check; returns its `watched/aired` right after, before the server answers. */
export async function tapSeason(viewer: Viewer, season: number): Promise<string> {
  await viewer.app.seasonCheck(season).click();
  return viewer.app.seasonProgress(season);
}

/** The show page's Watch next card, such as "S01|E02+3". */
export async function watchNext(viewer: Viewer): Promise<string> {
  return (await viewer.app.watchNext().getByTestId('episode-code').innerText()).replace(/\s+/g, '');
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

/** Whether confetti fell over the screen, within a second of the last tap. */
export async function confettiShown(viewer: Viewer): Promise<boolean> {
  return expect(viewer.app.confetti())
    .toBeAttached({ timeout: 1000 })
    .then(
      () => true,
      () => false,
    );
}

/** Whether the title's poster carries the Finished badge, in the Profile tab's row. */
export async function finishedBadgeOnProfile(viewer: Viewer, title: string): Promise<boolean> {
  await viewer.app.openTab('Profile');
  const item = viewer.app.profileItem('Shows', title);
  await expect(item).toBeVisible();
  return viewer.app.finishedBadge(item).isVisible();
}

/** The header's facts under the title, such as "1h 58m · May 1, 2020". */
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
  const item = viewer.app.libraryItem(title);
  await expect(item).toBeVisible();
  return (await item.getByTestId('tile-detail').innerText()).replace(/\s+/g, ' ').trim();
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
  await item.click();
  await expect(viewer.app.status('show-status')).toBeVisible();
  await viewer.app.back();
  // Other tests share the library and may add cards above it meanwhile: the card is checked on screen, not the pixel.
  const cardOnScreen = await expect(item)
    .toBeInViewport()
    .then(
      () => true,
      () => false,
    );
  return { scrolled, cardOnScreen };
}
