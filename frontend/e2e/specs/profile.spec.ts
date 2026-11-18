import { expect, test } from '../dsl/fixtures';
import {
  addMovie,
  choices,
  choose,
  libraryOfThree,
  openAndGoBack,
  profile,
  reload,
  seeAllShows,
  titles,
} from '../dsl/profile';
import { uniqueTitle } from '../dsl/tracking';

test('Profile shows the name, a row of shows and of movies, then the settings', async ({ viewer, admin }) => {
  // Given shows and a movie in the library
  const library = await libraryOfThree(viewer);
  const movie = uniqueTitle('Harbor Lights');
  await addMovie(viewer, movie);

  // When they open the Profile tab
  const shown = await profile(viewer);

  // Then it shows their name, their shows (last watched first) and movies, then the settings in groups
  expect(shown.name).toBe(admin.account.username);
  expect(shown.shows).toEqual([library.finished, library.watching, library.notStarted]);
  expect(shown.movies).toEqual([movie]);
  const groups = ['Account', 'Notifications', 'Integrations', 'Import history', 'Log out', 'Log out everywhere'];
  expect(shown.settings.filter((setting) => groups.includes(setting))).toEqual(groups);
  expect(shown.settings).toEqual(
    expect.arrayContaining(['Time zone', 'Change password', 'Jellyfin', 'API tokens', 'Choose a file and import']),
  );
  // Users are managed from the Admin tab.
  expect(shown.settings).not.toContain('Manage users');
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
