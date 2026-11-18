import { addFromTrending, openFirstResult, resultColumns, searchAmong, trending, TRENDING } from '../dsl/discover';
import { expect, test } from '../dsl/fixtures';
import { libraryEntry, uniqueTitle } from '../dsl/tracking';

test('without a query, Discover shows the trending shows and the trending movies', async ({ viewer }) => {
  expect(await trending(viewer, 'Trending shows')).toEqual(TRENDING);
  expect(await trending(viewer, 'Trending movies')).toEqual(TRENDING);
});

test('the + on a trending poster adds it in one tap and turns into a check', async ({ viewer }) => {
  // When they tap the + of a trending show and of a trending movie
  await trending(viewer, 'Trending shows');
  const show = await addFromTrending(viewer, 'Trending shows', TRENDING[0]);
  const movie = await addFromTrending(viewer, 'Trending movies', TRENDING[1]);

  // Then each turns into a check before the server answers, and stays one
  expect(show).toEqual({ checkAtOnce: true, checkAfter: true });
  expect(movie).toEqual({ checkAtOnce: true, checkAfter: true });

  // And both are in the library, to watch later
  expect(await libraryEntry(viewer, 'Shows', TRENDING[0])).toBe('0/5 · Watch later');
  expect(await libraryEntry(viewer, 'Movies', TRENDING[1])).toBe('Watch later');
});

test('a search finds only the type of its tab, which the address keeps', async ({ viewer }) => {
  const title = uniqueTitle('Glass Orchard');

  // Shows: the show only, opening the show's page
  const shows = await searchAmong(viewer, 'Shows', title);
  expect(shows.results).toEqual([title]);
  expect(shows.address).not.toContain('type=');

  // Movies: the movie only, and the address says so
  const movies = await searchAmong(viewer, 'Movies', title);
  expect(movies.results).toEqual([title]);
  expect(movies.address).toContain('type=movie');
  expect(await openFirstResult(viewer, title)).toBe('movie');
});

test('results are a grid of posters, three across on a phone', async ({ viewer }, testInfo) => {
  test.skip(testInfo.project.name !== 'phone', 'phone layout');
  await searchAmong(viewer, 'Shows', uniqueTitle('Grid Check'));

  expect(await resultColumns(viewer)).toBe(3);
});
