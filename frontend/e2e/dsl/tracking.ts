import { expect } from '@playwright/test';
import { Viewer } from './fixtures';

/** A title no other test uses: the fake TMDB serves one show and one movie per searched title. */
export function uniqueTitle(base: string, options: { ended?: boolean } = {}): string {
  const title = `${base} ${Math.random().toString(36).slice(2, 8)}`;
  return options.ended ? `Ended ${title}` : title;
}

export async function openShow(viewer: Viewer, title: string): Promise<void> {
  await viewer.app.search(title);
  await viewer.app.openResult(title, 'Show');
}

export async function openMovie(viewer: Viewer, title: string): Promise<void> {
  await viewer.app.search(title);
  await viewer.app.openResult(title, 'Movie');
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
  return (await viewer.app.episode(season, episode).getAttribute('aria-pressed')) === 'true';
}

/** Accept the offer to mark the earlier episodes and return what it said. */
export async function acceptEarlierEpisodes(viewer: Viewer): Promise<string> {
  return viewer.app.acceptPreviousOffer();
}

export async function markSeason(viewer: Viewer, season: number): Promise<void> {
  await viewer.app.seasonAction(season, 'Mark aired episodes watched');
}

export async function markMovieWatched(viewer: Viewer): Promise<string> {
  await viewer.app.clickButton('Mark watched');
  await expect(viewer.app.status('movie-status')).toHaveText('Watched');
  return (await viewer.app.status('movie-status').innerText()).trim();
}

/** A title's library card without its title: progress and status, such as "0/5 · Watch later". */
export async function libraryEntry(viewer: Viewer, type: 'Shows' | 'Movies', title: string): Promise<string> {
  await viewer.app.openLibrary(type);
  const item = viewer.app.libraryItem(title);
  await expect(item).toBeVisible();
  return (await item.innerText()).replace(title, '').replace(/\s+/g, ' ').trim();
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
