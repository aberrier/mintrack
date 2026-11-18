import { expect, Page } from '@playwright/test';
import { Viewer } from './fixtures';
import { uniqueTitle } from './tracking';

/** The fake TMDB's shows: season 1 has three aired episodes, season 2 two aired and one in a week. */
const AIRED: [number, number][] = [
  [1, 1],
  [1, 2],
  [1, 3],
  [2, 1],
  [2, 2],
];

/** A show the viewer watched up to `season`x`episode` (in airing order), under a title no other test uses. */
export async function showWatchedUpTo(viewer: Viewer, base: string, season: number, episode: number): Promise<string> {
  const title = uniqueTitle(base);
  const upTo = AIRED.findIndex(([s, e]) => s === season && e === episode);
  await viewer.api.markWatched(title, AIRED.slice(0, upTo + 1));
  return title;
}

/** Shows entirely watched, for a history of `count` × 5 episodes. */
export async function watchedShows(viewer: Viewer, count: number): Promise<void> {
  for (let index = 0; index < count; index++) await viewer.api.markWatched(uniqueTitle(`History ${index}`), AIRED);
}

export async function openWatchList(viewer: Viewer): Promise<void> {
  await viewer.app.openWatchList();
}

/** The episode a show's card offers next, such as "S01 | E02+3" (three more aired after it). */
export async function nextEpisodeOf(viewer: Viewer, show: string): Promise<string> {
  await expect(viewer.app.card(show)).toBeVisible();
  return viewer.app.cardEpisode(show);
}

export async function sectionOf(viewer: Viewer, show: string): Promise<string | null> {
  for (const name of ['Watch next', 'Haven’t watched for a while']) {
    if ((await viewer.app.watchListSection(name).getByTestId('episode').filter({ hasText: show }).count()) > 0)
      return name;
  }
  return null;
}

export async function check(viewer: Viewer, show: string): Promise<void> {
  await viewer.app.checkCard(show);
}

export async function isOnWatchList(viewer: Viewer, show: string): Promise<boolean> {
  return (await viewer.app.card(show).count()) > 0;
}

/** Take a show out of the watch list the way a phone user does (swipe) or a desktop user does (menu). */
export async function takeOut(
  viewer: Viewer,
  page: Page,
  show: string,
  action: 'Watch later' | 'Stop watching',
): Promise<void> {
  const touch = await page.evaluate(() => navigator.maxTouchPoints > 0);
  await viewer.app.cardAction(show, action, touch ? 'swipe' : 'menu');
}

/** Switch list and grid; returns whether the watch list is now a grid. */
export async function toggleView(viewer: Viewer): Promise<boolean> {
  await viewer.app.viewToggle().click();
  await viewer.app.rendered();
  return viewer.app.isGrid();
}

/** Scroll up past the top of the watch list, and wait for the history page it loads. */
export async function scrollUpIntoHistory(viewer: Viewer, page: Page): Promise<number> {
  const before = await viewer.app.historyEntries().count();
  const touch = await page.evaluate(() => navigator.maxTouchPoints > 0);
  if (before === 0) await viewer.app.scrollUpFromTop(touch);
  else await viewer.app.scrollToTop();
  await expect(viewer.app.historyEntries()).not.toHaveCount(before);
  return viewer.app.historyEntries().count();
}

export async function historyReachedItsStart(viewer: Viewer): Promise<boolean> {
  return viewer.app.history().getByTestId('history-start').isVisible();
}
