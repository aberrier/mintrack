import { expect, test } from '../dsl/fixtures';
import {
  addMovie,
  choices,
  choose,
  collectionSearch,
  libraryOfThree,
  mcpHelp,
  notificationsGuide,
  openAndGoBack,
  profile,
  reload,
  searchCollection,
  seeAllShows,
  settings,
  statistics,
  titles,
  watchAShowAndAMovie,
} from '../dsl/profile';
import { uniqueTitle } from '../dsl/tracking';

test('Profile shows the name, a row of shows and of movies; its gear opens the settings', async ({ viewer, admin }) => {
  // Given shows and a movie in the library
  const library = await libraryOfThree(viewer);
  const movie = uniqueTitle('Harbor Lights');
  await addMovie(viewer, movie);

  // When they open the Profile tab
  const shown = await profile(viewer);

  // Then it shows their name, their shows (last watched first) and movies, and no settings
  expect(shown.name).toBe(admin.account.username);
  expect(shown.shows).toEqual([library.finished, library.watching, library.notStarted]);
  expect(shown.movies).toEqual([movie]);
  expect(shown.hasSettings).toBe(false);

  // When they tap the gear, the settings open on their own page, in groups
  const shownSettings = await settings(viewer);
  const groups = [
    'Account',
    'Notifications',
    'Integrations',
    'Import history',
    'Connected devices',
    'Log out',
    'Log out everywhere',
  ];
  expect(shownSettings.filter((setting) => groups.includes(setting))).toEqual(groups);
  expect(shownSettings).toEqual(
    expect.arrayContaining(['Time zone', 'Change password', 'Jellyfin', 'API tokens', 'Choose a file and import']),
  );
  // Users are managed from the Admin tab.
  expect(shownSettings).not.toContain('Manage users');
});

test('Learn more explains how to connect an assistant to this server', async ({ viewer }) => {
  const shown = await mcpHelp(viewer);

  expect(shown.url).toBe(new URL('/mcp', viewer.app.url()).href);
  expect(JSON.parse(shown.json)).toEqual({
    mcpServers: { mintrack: { type: 'http', url: shown.url, headers: { Authorization: 'Bearer YOUR_TOKEN' } } },
  });
  expect(shown.command).toBe(
    `claude mcp add --transport http mintrack ${shown.url} --header "Authorization: Bearer YOUR_TOKEN"`,
  );
});

test('the notifications guide shows the steps for this phone first, then the other', async ({
  viewer,
  browserName,
}) => {
  const sections = await notificationsGuide(viewer);

  const android = 'Android (Chrome)';
  const iphone = 'iPhone (iOS 16.4 or later)';
  // Chromium runs as an Android phone or a desktop, WebKit as an iPhone.
  const phones = browserName === 'webkit' ? [iphone, android] : [android, iphone];
  expect(sections).toEqual([...phones, 'Check it', 'Requirements']);
});

test('See all opens a grid sorted and filtered by progress, both kept in the address', async ({ viewer }) => {
  // Given three shows: one being watched, one not started, one finished
  const library = await libraryOfThree(viewer);

  // When they open all their shows, the last watched come first
  await seeAllShows(viewer);
  await expect.poll(() => titles(viewer)).toEqual([library.finished, library.watching, library.notStarted]);

  // Sorted by last added, then A–Z
  await choose(viewer, 'Sort by', 'Last added');
  await expect.poll(() => titles(viewer)).toEqual([library.finished, library.notStarted, library.watching]);
  await choose(viewer, 'Sort by', 'A–Z');
  await expect.poll(() => titles(viewer)).toEqual([library.watching, library.notStarted, library.finished]);

  // Filtered by progress
  await choose(viewer, 'Progress', 'Haven’t started');
  await expect.poll(() => titles(viewer)).toEqual([library.notStarted]);
  await choose(viewer, 'Progress', 'Watching');
  await expect.poll(() => titles(viewer)).toEqual([library.watching]);
  const address = await choose(viewer, 'Progress', 'Finished');
  await expect.poll(() => titles(viewer)).toEqual([library.finished]);

  // Then the address keeps both choices, coming back from a title or opening it again shows the same grid
  expect(address).toContain('sort=title');
  expect(address).toContain('progress=finished');
  await openAndGoBack(viewer, library.finished);
  await expect.poll(() => choices(viewer)).toEqual(['A–Z', 'Finished']);
  await reload(viewer);
  await expect.poll(() => choices(viewer)).toEqual(['A–Z', 'Finished']);
  await expect.poll(() => titles(viewer)).toEqual([library.finished]);
});

test('searching the collection by title narrows the grid, the search kept in the address', async ({ viewer }) => {
  // Given three shows
  const library = await libraryOfThree(viewer);
  await seeAllShows(viewer);

  // When they search for part of a title, in another case
  const address = await searchCollection(viewer, 'birch');

  // Then only that show is listed, also after a reload
  await expect.poll(() => titles(viewer)).toEqual([library.notStarted]);
  expect(address).toContain('q=birch');
  await reload(viewer);
  expect(await collectionSearch(viewer)).toBe('birch');
  await expect.poll(() => titles(viewer)).toEqual([library.notStarted]);
});

test('Statistics count the time spent, the totals, the streak and the top genres and networks', async ({ viewer }) => {
  // Given nothing watched, Statistics says so
  expect(await statistics(viewer)).toBeNull();

  // Given two 45-minute episodes and a 118-minute movie watched today
  await watchAShowAndAMovie(viewer);

  // When they open Statistics
  const shown = await statistics(viewer);

  // Then it adds up the runtimes, counts the titles, starts a streak and ranks genres and networks
  expect(shown?.time).toBe('3h 28m');
  expect(shown?.figures).toMatchObject({
    Shows: '1',
    'Finished shows': '0',
    Episodes: '2',
    Movies: '1',
    'Current streak': '1 day',
    'Longest streak': '1 day',
  });
  expect(shown?.months).toHaveLength(12);
  expect(shown?.months.at(-1)).toMatch(/, episodes: 2, movies: 1$/);
  expect(shown?.genres).toEqual(['Drama', 'Action', 'Mystery']);
  expect(shown?.networks).toEqual(['Channel Nine']);
});
