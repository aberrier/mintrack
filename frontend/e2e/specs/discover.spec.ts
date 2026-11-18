import {
  addedAfterReload,
  addFromTrending,
  clearSearch,
  openFirstResult,
  resultColumns,
  searchAmong,
  trending,
  TRENDING,
  trendingKinds,
} from '../dsl/discover';
import { expect, test } from '../dsl/fixtures';
import { libraryEntry, uniqueTitle } from '../dsl/tracking';
import { nextEpisodeOf, openWatchList, sectionOf } from '../dsl/watch-list';

test('without a query, Discover shows the trending shows and the trending movies', async ({ viewer }) => {
  expect(await trending(viewer, 'Trending shows')).toEqual(TRENDING);
  expect(await trending(viewer, 'Trending movies')).toEqual(TRENDING);

  // The fake TMDB trends the same titles as both: each row opens its own kind of page.
  expect(await trendingKinds(viewer, 'Trending shows')).toEqual(['show']);
  expect(await trendingKinds(viewer, 'Trending movies')).toEqual(['movie']);
});

test('the + on a trending poster adds it in one tap and turns into a check', async ({ viewer }) => {
  // When they tap the + of a trending show and of a trending movie
  await trending(viewer, 'Trending shows');
  const show = await addFromTrending(viewer, 'Trending shows', TRENDING[0]);
  const movie = await addFromTrending(viewer, 'Trending movies', TRENDING[1]);

  // Then each turns into a check before the server answers, and stays one, also when Discover opens again
  expect(show).toEqual({ checkAtOnce: true, checkAfter: true });
  expect(movie).toEqual({ checkAtOnce: true, checkAfter: true });
  expect(await addedAfterReload(viewer, 'Trending shows', TRENDING[0])).toBe(true);

  // And both are in the library: the show not started yet, the movie to watch later
  expect(await libraryEntry(viewer, 'Shows', TRENDING[0])).toBe('0/5 · Haven’t started');
  expect(await libraryEntry(viewer, 'Movies', TRENDING[1])).toBe('Watch later');
});

test('a show added from Discover waits on the watch list under Haven’t started, at its first episode', async ({
  viewer,
}) => {
  await trending(viewer, 'Trending shows');
  await addFromTrending(viewer, 'Trending shows', TRENDING[0]);

  await openWatchList(viewer);

  expect(await sectionOf(viewer, TRENDING[0])).toBe('Haven’t started');
  expect(await nextEpisodeOf(viewer, TRENDING[0])).toBe('S01|E01+4');
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

test('clearing the search brings the trending rows back', async ({ viewer }) => {
  await searchAmong(viewer, 'Shows', uniqueTitle('Cleared Away'));

  expect(await clearSearch(viewer)).toEqual({ results: 0, trending: TRENDING });
});

test('results are a grid of posters, three across on a phone', async ({ viewer }, testInfo) => {
  test.skip(testInfo.project.name !== 'phone', 'phone layout');
  await searchAmong(viewer, 'Shows', uniqueTitle('Grid Check'));

  expect(await resultColumns(viewer)).toBe(3);
});
