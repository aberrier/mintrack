import { expect, test } from '../dsl/fixtures';
import { headerFacts, movieStatus, openMovie, tapMovieCheck, today, uniqueTitle } from '../dsl/tracking';

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
