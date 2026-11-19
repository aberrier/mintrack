import { expect, test } from '../dsl/fixtures';
import {
  digitalRelease,
  headerFacts,
  movieStatus,
  openMovie,
  tapMovieCheck,
  today,
  uniqueTitle,
  yesterday,
} from '../dsl/tracking';

test('the movie page shows its runtime and release date, and one check marks and unmarks it', async ({ viewer }) => {
  // Given a movie found by searching
  const title = uniqueTitle('Silver Ferry');
  await openMovie(viewer, title);
  expect(await headerFacts(viewer)).toBe('1h 58m · 1 May 2020');

  // When they tap its check, it is watched today (the year goes without saying)
  expect(await tapMovieCheck(viewer)).toBe(`Watched ${await today(viewer)}`);
  await expect.poll(() => movieStatus(viewer)).toBe('Watched');

  // When they tap it again, it is no longer watched and waits in the library
  expect(await tapMovieCheck(viewer)).toBe('Not watched');
  await expect.poll(() => movieStatus(viewer)).toBe('Watch later');
});

test('the movie page shows its first digital release, in whichever country', async ({ viewer }) => {
  // Given a movie released digitally yesterday in one country and next month in another
  await openMovie(viewer, uniqueTitle('Digital Harbour'));

  // Then its page shows the earliest one
  await expect.poll(() => digitalRelease(viewer)).toBe(`Digital release: ${yesterday()}`);

  // And a movie released only in theatres shows none
  await openMovie(viewer, uniqueTitle('Cinema Harbour'));
  await expect(viewer.app.movieCheck()).toBeVisible();
  expect(await digitalRelease(viewer)).toBeNull();
});
