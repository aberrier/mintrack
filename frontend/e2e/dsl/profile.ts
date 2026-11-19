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

/** What the Profile tab shows: the user's name, the titles of each row, and whether it holds settings. */
export async function profile(
  viewer: Viewer,
): Promise<{ name: string; shows: string[]; movies: string[]; hasSettings: boolean }> {
  await viewer.app.openTab('Profile');
  const shows = await viewer.app.profileTitles('Shows');
  const movies = await viewer.app.profileTitles('Movies');
  return {
    name: (await viewer.app.heading().innerText()).trim(),
    shows,
    movies,
    hasSettings: (await viewer.app.logOutButtons().count()) > 0,
  };
}

/** The Settings page, from the Profile tab's gear: its headings and buttons, in order. */
export async function settings(viewer: Viewer): Promise<string[]> {
  await viewer.app.openSettings();
  await viewer.app.settingsLoaded();
  return viewer.app.settings();
}

/** Open the MCP help from the API tokens settings; returns its server address, configuration and command. */
export async function mcpHelp(viewer: Viewer): Promise<{ url: string; json: string; command: string }> {
  await viewer.app.openMcpHelp();
  return {
    url: await viewer.app.mcpSample('url'),
    json: await viewer.app.mcpSample('json'),
    command: await viewer.app.mcpSample('command'),
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

/** Type in the collection's search field; returns the address's query once it follows. */
export async function searchCollection(viewer: Viewer, text: string): Promise<string> {
  await viewer.app.searchLibrary(text);
  await expect.poll(() => new URL(viewer.app.url()).searchParams.get('q')).toBe(text);
  return new URL(viewer.app.url()).search;
}

/** What the collection's search field holds. */
export async function collectionSearch(viewer: Viewer): Promise<string> {
  return viewer.app.librarySearch().inputValue();
}

/** The collection grid's titles, in order. */
export async function titles(viewer: Viewer): Promise<string[]> {
  return viewer.app.libraryTitles();
}

/** Which Sort by and Progress choices are selected. */
export async function choices(viewer: Viewer): Promise<string[]> {
  return viewer.app.selectedLibraryChoices();
}

/** Open a title of the collection, then go back to it. */
export async function openAndGoBack(viewer: Viewer, title: string): Promise<void> {
  await viewer.app.openLibraryItem(title);
  await viewer.app.back();
  await expect(viewer.app.libraryItem(title)).toBeVisible();
}

export async function reload(viewer: Viewer): Promise<void> {
  await viewer.app.reload();
}
