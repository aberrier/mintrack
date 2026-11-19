import { addFromTrending, trending, TRENDING } from '../dsl/discover';
import { recordVibrations, testVibration, turnVibrationOff, vibrationOffered, vibrations } from '../dsl/feedback';
import { expect, test } from '../dsl/fixtures';
import { closeEpisode, openEpisode, tapSheetCheck } from '../dsl/ratings';
import {
  addShow,
  answerUnmark,
  checkWatchNext,
  isSeasonWatched,
  markMovieWatched,
  openMovie,
  openShow,
  tapEpisode,
  tapSeason,
  tapWatchedSeason,
  uniqueTitle,
} from '../dsl/tracking';
import { check, openWatchList, showWatchedUpTo } from '../dsl/watch-list';

/** One tap's vibration, asked for while the tap was being handled, long enough to be felt. */
const TAP = 30;

test('every tap that changes the library vibrates once, while the tap is handled', async ({ viewer }) => {
  // Given a phone that can vibrate from a web page (Android; an iPhone cannot)
  test.skip(!(await recordVibrations(viewer)), 'This browser cannot vibrate');

  // When they add a show, then mark an episode, the Watch next card, a season, and unmark the season
  await openShow(viewer, uniqueTitle('Buzz Added'));
  await addShow(viewer);
  expect(await vibrations(viewer)).toEqual([TAP]);
  await tapEpisode(viewer, 1, 1);
  expect(await vibrations(viewer)).toEqual([TAP]);
  await checkWatchNext(viewer);
  expect(await vibrations(viewer)).toEqual([TAP]);
  await tapSeason(viewer, 1);
  expect(await vibrations(viewer)).toEqual([TAP]);
  await tapWatchedSeason(viewer, 1);
  await answerUnmark(viewer, 'Unmark');
  await expect.poll(() => isSeasonWatched(viewer, 1)).toBe(false);
  expect(await vibrations(viewer)).toEqual([TAP]);

  // And so do the episode sheet's check, a movie's check and the + of a trending poster
  await openEpisode(viewer, 1, 2);
  await tapSheetCheck(viewer);
  expect(await vibrations(viewer)).toEqual([TAP]);
  await closeEpisode(viewer);
  await openMovie(viewer, uniqueTitle('Buzz Movie'));
  await markMovieWatched(viewer);
  expect(await vibrations(viewer)).toEqual([TAP]);
  await trending(viewer, 'Trending shows');
  await addFromTrending(viewer, 'Trending shows', TRENDING[0]);
  expect(await vibrations(viewer)).toEqual([TAP]);
});

test('a watch list check vibrates, until vibration is turned off in Settings', async ({ viewer }) => {
  test.skip(!(await recordVibrations(viewer)), 'This browser cannot vibrate');
  const watching = await showWatchedUpTo(viewer, 'Buzzing Along', 1, 1);

  await openWatchList(viewer);
  await check(viewer, watching);
  expect(await vibrations(viewer)).toEqual([TAP]);

  // When they turn vibration off, a check vibrates no more
  await turnVibrationOff(viewer);
  await openWatchList(viewer);
  await check(viewer, watching);
  expect(await vibrations(viewer)).toEqual([]);

  // But Settings' test still vibrates the tap's tick, then a long buzz, to tell whether the phone vibrates at all
  await testVibration(viewer);
  expect(await vibrations(viewer)).toEqual([[TAP, 400, 300]]);
});

test.describe('with reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });

  test('a check still vibrates: a vibration moves nothing on screen', async ({ viewer }) => {
    test.skip(!(await recordVibrations(viewer)), 'This browser cannot vibrate');
    const watching = await showWatchedUpTo(viewer, 'Quiet Phone', 1, 1);

    await openWatchList(viewer);
    await check(viewer, watching);

    expect(await vibrations(viewer)).toEqual([TAP]);
  });
});

test('Settings offers the vibration switch only where the phone can vibrate', async ({ viewer }) => {
  const canVibrate = await recordVibrations(viewer);

  expect(await vibrationOffered(viewer)).toBe(canVibrate);
});
