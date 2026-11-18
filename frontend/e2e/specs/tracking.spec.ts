import { expect, test } from '../dsl/fixtures';
import {
  acceptEarlierEpisodes,
  addShow,
  isWatched,
  libraryEntry,
  markMovieWatched,
  markSeason,
  openAndComeBack,
  openMovie,
  openShow,
  seedShows,
  showStatus,
  tapEpisode,
  uniqueTitle,
} from '../dsl/tracking';

test('someone finds a show and adds it to watch later', async ({ viewer }) => {
  // Given a show found by searching
  const title = uniqueTitle('Orbit Kitchen');
  await openShow(viewer, title);

  // When they add it to their library
  const status = await addShow(viewer);

  // Then it waits there to be watched: nothing watched out of five aired episodes
  expect(status).toBe('Watch later');
  expect(await libraryEntry(viewer, 'Shows', title)).toBe('0/5 · Watch later');
});

test('someone marks and unmarks an episode in one tap each', async ({ viewer }) => {
  // Given an untracked show
  const title = uniqueTitle('Lighthouse Nights');
  await openShow(viewer, title);

  // When they tap an episode, the show is being watched
  await tapEpisode(viewer, 1, 1);
  expect(await showStatus(viewer)).toBe('Watching');

  // When they tap it again, it is no longer watched
  await tapEpisode(viewer, 1, 1);
  expect(await isWatched(viewer, 1, 1)).toBe(false);
  await expect.poll(() => showStatus(viewer)).toBe('Watch later');
});

test('someone catches up on the earlier episodes when skipping ahead', async ({ viewer }) => {
  // Given a show whose only unaired episode is the last one
  const title = uniqueTitle('Paper Boats');
  await openShow(viewer, title);

  // When they mark the latest aired episode and accept the offer for the earlier ones
  await tapEpisode(viewer, 2, 2);
  const offer = await acceptEarlierEpisodes(viewer);

  // Then every aired episode is watched and the show is up to date
  expect(offer).toBe('4 earlier episodes are not watched.');
  await expect.poll(() => isWatched(viewer, 1, 1)).toBe(true);
  await expect.poll(() => showStatus(viewer)).toBe('Up to date');
});

test('someone marks whole seasons of an ended show and finishes it', async ({ viewer }) => {
  // Given an ended show
  const title = uniqueTitle('Quiet Harbour', { ended: true });
  await openShow(viewer, title);

  // When they mark both seasons from the season menus
  await markSeason(viewer, 1);
  await markSeason(viewer, 2);

  // Then the show is finished
  await expect.poll(() => showStatus(viewer)).toBe('Finished');
  expect(await libraryEntry(viewer, 'Shows', title)).toBe('6/6 · Finished');
});

test('someone marks a movie watched', async ({ viewer }) => {
  const title = uniqueTitle('Paper Moons');
  await openMovie(viewer, title);

  expect(await markMovieWatched(viewer)).toBe('Watched');
  expect(await libraryEntry(viewer, 'Movies', title)).toBe('Watched');
});

test('back to the library keeps its scroll position', async ({ viewer }) => {
  // Given a library longer than the screen
  const titles = Array.from({ length: 30 }, (_, index) => uniqueTitle(`Long List ${index}`));
  await seedShows(viewer, titles);
  // The oldest change comes last in the library.
  await libraryEntry(viewer, 'Shows', titles[0]);

  // When they open a show far down the list and come back
  const { scrolled, cardOnScreen } = await openAndComeBack(viewer, titles[0]);

  // Then the list is where they left it
  expect(scrolled).toBeGreaterThan(0);
  expect(cardOnScreen).toBe(true);
});
