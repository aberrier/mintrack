import { expect, Locator } from '@playwright/test';
import { Viewer } from './fixtures';

/** The titles the fake TMDB lists as trending, as shows and as movies. */
export const TRENDING = ['Trending One', 'Trending Two'];

type Row = 'Trending shows' | 'Trending movies';

/** The titles of a trending row, from the Discover tab without a query. */
export async function trending(viewer: Viewer, row: Row): Promise<string[]> {
  await viewer.app.openTab('Discover');
  return viewer.app.trendingTitles(row);
}

/**
 * Tap the `+` on a trending poster; returns whether it turned into a check at once, before the server answered, and
 * whether it is still one once it did.
 */
export async function addFromTrending(
  viewer: Viewer,
  row: Row,
  title: string,
): Promise<{ checkAtOnce: boolean; checkAfter: boolean }> {
  const within = viewer.app.trendingRow(row);
  let release: () => void = () => undefined;
  // The request waits until the screen has been read.
  await viewer.app.holdRequests('/tracking', new Promise<void>((resolve) => (release = resolve)));
  const saved = viewer.app.nextResponse('/tracking');
  await viewer.app.posterAdd(within, title).click();
  const checkAtOnce = await shown(viewer.app.posterAdded(within, title));
  release();
  await saved;
  return { checkAtOnce, checkAfter: await shown(viewer.app.posterAdded(within, title)) };
}

/** Which kinds of page a trending row's posters open: show, movie or both. */
export async function trendingKinds(viewer: Viewer, row: Row): Promise<('show' | 'movie')[]> {
  const links = await viewer.app.trendingLinks(row);
  return [...new Set(links.map((link) => (link.startsWith('/shows/') ? 'show' : 'movie')))];
}

/** Whether the title's poster still shows the check once Discover is loaded again from the server. */
export async function addedAfterReload(viewer: Viewer, row: Row, title: string): Promise<boolean> {
  await viewer.app.reload();
  await viewer.app.openTab('Discover');
  return shown(viewer.app.posterAdded(viewer.app.trendingRow(row), title));
}

/** Empty the search field; returns how many results are left and the trending shows shown again. */
export async function clearSearch(viewer: Viewer): Promise<{ results: number; trending: string[] }> {
  await viewer.app.clearSearch();
  const trending = await viewer.app.trendingTitles('Trending shows');
  return { results: await viewer.app.searchResults().count(), trending };
}

function shown(locator: Locator): Promise<boolean> {
  return expect(locator)
    .toBeVisible()
    .then(
      () => true,
      () => false,
    );
}

/** Search among shows or movies; returns the titles found and the address's query. */
export async function searchAmong(
  viewer: Viewer,
  type: 'Shows' | 'Movies',
  query: string,
): Promise<{ results: string[]; address: string }> {
  await viewer.app.search(query, type);
  return { results: await viewer.app.searchResultTitles(), address: new URL(viewer.app.url()).search };
}

/** Open the first search result and say which kind of page opened. */
export async function openFirstResult(viewer: Viewer, title: string): Promise<'show' | 'movie'> {
  await viewer.app.openResult(title);
  return new URL(viewer.app.url()).pathname.startsWith('/shows/') ? 'show' : 'movie';
}

export async function resultColumns(viewer: Viewer): Promise<number> {
  return viewer.app.resultColumns();
}
