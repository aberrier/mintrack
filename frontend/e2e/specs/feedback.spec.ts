import { recordVibrations, turnVibrationOff, vibrationOffered, vibrations } from '../dsl/feedback';
import { expect, test } from '../dsl/fixtures';
import { addShow, openShow, tapSeason, uniqueTitle } from '../dsl/tracking';
import { check, openWatchList, showWatchedUpTo } from '../dsl/watch-list';

test('checks and adding a show vibrate briefly, until vibration is turned off in Settings', async ({ viewer }) => {
  // Given a phone that can vibrate from a web page (Android; an iPhone cannot)
  test.skip(!(await recordVibrations(viewer)), 'This browser cannot vibrate');
  const watching = await showWatchedUpTo(viewer, 'Buzzing Along', 1, 1);

  // When they add a show and mark a season, each tap vibrates once, briefly
  await openShow(viewer, uniqueTitle('Buzz Added'));
  await addShow(viewer);
  await tapSeason(viewer, 1);
  expect(await vibrations(viewer)).toEqual([15, 15]);

  // And so does checking a card of the watch list
  await openWatchList(viewer);
  await check(viewer, watching);
  expect(await vibrations(viewer)).toEqual([15]);

  // When they turn vibration off, a check vibrates no more
  await turnVibrationOff(viewer);
  await openWatchList(viewer);
  await check(viewer, watching);
  expect(await vibrations(viewer)).toEqual([]);
});

test.describe('with reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });

  test('a check does not vibrate', async ({ viewer }) => {
    test.skip(!(await recordVibrations(viewer)), 'This browser cannot vibrate');
    const watching = await showWatchedUpTo(viewer, 'Quiet Phone', 1, 1);

    await openWatchList(viewer);
    await check(viewer, watching);

    expect(await vibrations(viewer)).toEqual([]);
  });
});

test('Settings offers the vibration switch only where the phone can vibrate', async ({ viewer }) => {
  const canVibrate = await recordVibrations(viewer);

  expect(await vibrationOffered(viewer)).toBe(canVibrate);
});
