import { expect, test } from '../dsl/fixtures';
import { headerFacts, movieStatus, openMovie, tapMovieCheck, uniqueTitle } from '../dsl/tracking';

test('the movie page shows its runtime and release date, and one check marks and unmarks it', async ({ viewer }) => {
  // Given a movie found by searching
  const title = uniqueTitle('Silver Ferry');
  await openMovie(viewer, title);
  expect(await headerFacts(viewer)).toBe('1h 58m · May 1, 2020');

  // When they tap its check, it is watched today
  const today = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(new Date());
  expect(await tapMovieCheck(viewer)).toBe(`Watched ${today}`);
  await expect.poll(() => movieStatus(viewer)).toBe('Watched');

  // When they tap it again, it is no longer watched and waits in the library
  expect(await tapMovieCheck(viewer)).toBe('Not watched');
  await expect.poll(() => movieStatus(viewer)).toBe('Watch later');
});
