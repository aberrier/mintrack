import { expect, test } from '../dsl/fixtures';
import {
  acceptEarlierEpisodes,
  addShow,
  answerUnmark,
  checkWatchNext,
  confettiShown,
  finishedBadgeOnProfile,
  isSeasonWatched,
  isWatched,
  libraryEntry,
  markMovieWatched,
  openAndComeBack,
  openMovie,
  openShow,
  seasonProgress,
  seedShows,
  showStatus,
  tapEpisode,
  tapSeason,
  uniqueTitle,
  watchNext,
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

test('someone marks a season in one tap, and unmarks it only after confirming', async ({ viewer }) => {
  // Given a running show whose second season still has an episode to air
  const title = uniqueTitle('Lantern Row');
  await openShow(viewer, title);

  // When they tap each season's check
  const first = await tapSeason(viewer, 1);
  const second = await tapSeason(viewer, 2);

  // Then every aired episode is marked at once, the unaired one is left
  expect([first, second]).toEqual(['3/3', '2/2']);
  expect(await isSeasonWatched(viewer, 1)).toBe(true);
  await expect.poll(() => showStatus(viewer)).toBe('Up to date');

  // When they tap the watched season again, a question comes first: cancelling keeps it
  await tapSeason(viewer, 1);
  await answerUnmark(viewer, 'Cancel');
  expect(await seasonProgress(viewer, 1)).toBe('3/3');

  // And confirming unmarks it
  await tapSeason(viewer, 1);
  await answerUnmark(viewer, 'Unmark');
  expect(await seasonProgress(viewer, 1)).toBe('0/3');
  await expect.poll(() => showStatus(viewer)).toBe('Watching');
});

test('finishing an ended show throws confetti and puts the Finished badge on its poster', async ({ viewer }) => {
  // Given an ended show
  const title = uniqueTitle('Quiet Harbour', { ended: true });
  await openShow(viewer, title);

  // When they mark both seasons, the second holding the last aired episode
  await tapSeason(viewer, 1);
  expect(await confettiShown(viewer)).toBe(false);
  await tapSeason(viewer, 2);

  // Then confetti falls, and the show is finished, with the badge on its poster
  expect(await confettiShown(viewer)).toBe(true);
  await expect.poll(() => showStatus(viewer)).toBe('Finished');
  expect(await libraryEntry(viewer, 'Shows', title)).toBe('6/6 · Finished');
  expect(await finishedBadgeOnProfile(viewer, title)).toBe(true);
});

test.describe('with reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });

  test('finishing a show throws no confetti', async ({ viewer }) => {
    const title = uniqueTitle('Still Water', { ended: true });
    await openShow(viewer, title);

    await tapSeason(viewer, 1);
    await tapSeason(viewer, 2);

    await expect.poll(() => showStatus(viewer)).toBe('Finished');
    expect(await confettiShown(viewer)).toBe(false);
  });
});

test('the Watch next card marks the next episode in one tap', async ({ viewer }) => {
  // Given a show with its first episode watched
  const title = uniqueTitle('Copper Line');
  await openShow(viewer, title);
  await tapEpisode(viewer, 1, 1);
  expect(await watchNext(viewer)).toBe('S01|E02+3');

  // When they tap the card's check, it moves on to the next episode
  await checkWatchNext(viewer);
  expect(await watchNext(viewer)).toBe('S01|E03+2');
  expect(await isWatched(viewer, 1, 2)).toBe(true);
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
