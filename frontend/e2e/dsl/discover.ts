import { expect, Locator } from '@playwright/test';
import { Viewer } from './fixtures';

/** The titles the fake TMDB lists as trending, as shows and as movies. */
export const TRENDING = ['Trending One', 'Trending Two'];

type Row = 'Trending shows' | 'Trending movies';

/** The titles of a trending row, from the Discover tab without a query. */
export async function trending(viewer: Viewer, row: Row): Promise<string[]> {
  await viewer.app.openTab('Discover');
  const items = viewer.app.trendingRow(row).getByTestId('trending-item');
  await expect(items.first()).toBeVisible();
  return (await items.getByRole('link').allInnerTexts()).map((title) => title.trim());
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
  const results = (await viewer.app.searchResults().getByRole('link').allInnerTexts()).map((title) => title.trim());
  return { results, address: new URL(viewer.app.url()).search };
}

/** Open the first search result and say which kind of page opened. */
export async function openFirstResult(viewer: Viewer, title: string): Promise<'show' | 'movie'> {
  await viewer.app.openResult(title);
  return new URL(viewer.app.url()).pathname.startsWith('/shows/') ? 'show' : 'movie';
}

export async function resultColumns(viewer: Viewer): Promise<number> {
  return viewer.app.resultColumns();
}
