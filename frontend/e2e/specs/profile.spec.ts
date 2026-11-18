import { expect, test } from '../dsl/fixtures';
import { addMovie, choices, choose, libraryOfThree, profile, reload, seeAllShows, titles } from '../dsl/profile';
import { uniqueTitle } from '../dsl/tracking';

test('Profile shows the name, a row of shows and of movies, then the settings', async ({ viewer, admin }) => {
  // Given shows and a movie in the library
  const library = await libraryOfThree(viewer);
  const movie = uniqueTitle('Harbor Lights');
  await addMovie(viewer, movie);

  // When they open the Profile tab
  const shown = await profile(viewer);

  // Then it shows their name, their shows (last watched first) and movies, then every setting
  expect(shown.name).toBe(admin.account.username);
  expect(shown.shows).toEqual([library.finished, library.watching, library.notStarted]);
  expect(shown.movies).toEqual([movie]);
  expect(shown.settings).toEqual(
    expect.arrayContaining([
      'Time zone',
      'Change password',
      'Notifications',
      'Jellyfin',
      'Import your history',
      'API tokens',
      'Manage users',
      'Log out',
      'Log out everywhere',
    ]),
  );
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

  // Then the address keeps both choices, and opening it again shows the same grid
  expect(address).toContain('sort=title');
  expect(address).toContain('progress=finished');
  await reload(viewer);
  await expect.poll(() => choices(viewer)).toEqual(['A–Z', 'Finished']);
  await expect.poll(() => titles(viewer)).toEqual([library.finished]);
});
