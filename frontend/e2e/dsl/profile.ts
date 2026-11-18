import { expect } from '@playwright/test';
import { Viewer } from './fixtures';
import { uniqueTitle } from './tracking';

const ALL_AIRED: [number, number][] = [
  [1, 1],
  [1, 2],
  [1, 3],
  [2, 1],
  [2, 2],
  [2, 3],
];

export interface Library {
  /** One episode watched. */
  watching: string;
  /** Added, nothing watched. */
  notStarted: string;
  /** Ended, every episode watched: added and watched last. */
  finished: string;
}

/** Three shows added one after the other, whose titles sort in the order of the fields. */
export async function libraryOfThree(viewer: Viewer): Promise<Library> {
  const library = {
    watching: uniqueTitle('Amber Lane'),
    notStarted: uniqueTitle('Birch Hall'),
    finished: uniqueTitle('Cedar Court', { ended: true }),
  };
  await viewer.api.markWatched(library.watching, [[1, 1]]);
  const notStarted = await viewer.api.findShow(library.notStarted);
  expect((await viewer.api.loadShow(notStarted)).ok()).toBe(true);
  expect((await viewer.api.addShow(notStarted)).ok()).toBe(true);
  await viewer.api.markWatched(library.finished, ALL_AIRED);
  return library;
}

export async function addMovie(viewer: Viewer, title: string): Promise<void> {
  await viewer.api.addMovie(title);
}

/** What the Profile tab shows: the user's name, the titles of each row, and its settings. */
export async function profile(
  viewer: Viewer,
): Promise<{ name: string; shows: string[]; movies: string[]; settings: string[] }> {
  await viewer.app.openTab('Profile');
  const row = async (type: 'Shows' | 'Movies') => {
    const items = viewer.app.profileRow(type).getByTestId('profile-item');
    await expect(items.first()).toBeVisible();
    return (await items.getByRole('link').allInnerTexts()).map((title) => title.trim());
  };
  const shows = await row('Shows');
  const movies = await row('Movies');
  return {
    name: (await viewer.app.heading().innerText()).trim(),
    shows,
    movies,
    settings: await viewer.app.settings(),
  };
}

export async function seeAllShows(viewer: Viewer): Promise<void> {
  await viewer.app.openLibrary('Shows');
}

/** Pick a Sort by or Progress choice; returns the address's query. */
export async function choose(viewer: Viewer, group: 'Sort by' | 'Progress', choice: string): Promise<string> {
  await viewer.app.chooseLibrary(group, choice);
  return new URL(viewer.app.url()).search;
}

/** The collection grid's titles, in order. */
export async function titles(viewer: Viewer): Promise<string[]> {
  return viewer.app.libraryTitles();
}

/** Which Sort by and Progress choices are selected. */
export async function choices(viewer: Viewer): Promise<string[]> {
  return viewer.app.selectedLibraryChoices();
}

export async function reload(viewer: Viewer): Promise<void> {
  await viewer.app.reload();
}
