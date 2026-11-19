import { expect, test } from '../dsl/fixtures';
import {
  dayOf,
  emptyMessage,
  episodeOn,
  fitsTheWidth,
  months,
  openUpcoming,
  posterShown,
  serveUpcoming,
  toggleView,
} from '../dsl/upcoming';
import { openWatchList, showWatchedUpTo } from '../dsl/watch-list';

test('someone following no show is told what Watch list and Upcoming will show', async ({ viewer }) => {
  // An empty library points to adding shows or importing a history
  await openWatchList(viewer);
  expect(await emptyMessage(viewer)).toContain('bring your history from another tracker');

  expect(await openUpcoming(viewer)).toBe(true);
  expect(await emptyMessage(viewer)).toContain('Nothing airs in the next four weeks');
});

test('a followed show’s next episode is listed under its air day, named by its date beyond this week', async ({
  viewer,
}) => {
  // Given a show being watched whose last episode airs in a week
  const show = await showWatchedUpTo(viewer, 'Coming Soon', 1, 1);

  // When they open Upcoming
  await openUpcoming(viewer);

  // Then the episode is under its day, which, a week away, is past Sunday: a date such as "26 November"
  const day = await dayOf(viewer, show);
  expect(day).toMatch(/^\d{1,2} [A-Z][a-z]+( \d{4})?$/);
  expect((await episodeOn(viewer, day, show)).code).toBe('S02|E03');
});

test('upcoming episodes fit the screen, by day and month, in a list or a grid', async ({ viewer }) => {
  const episode = {
    tmdb_id: 1,
    poster_path: null,
    season_number: 1,
    episode_number: 2,
    title: 'An episode title long enough to be cut on a phone screen without any horizontal scrolling',
    airstamp: '2099-01-02T20:00:00Z',
    day: '2099-01-02',
  };
  await serveUpcoming(viewer, {
    time_zone: 'UTC',
    days: [{ day: '2099-01-02', episodes: [{ ...episode, episode_id: 'next', show_title: 'Next show' }] }],
  });

  await openUpcoming(viewer);

  expect(await months(viewer)).toEqual(['January 2099']);
  expect(await episodeOn(viewer, '2 January 2099', 'Next show')).toEqual({ code: 'S01|E02', time: '20:00' });
  expect(await fitsTheWidth(viewer)).toBe(true);

  await toggleView(viewer);
  expect(await posterShown(viewer, '2 January 2099', 'Next show, season 1 episode 2, An episode title')).toBe(true);
  expect(await fitsTheWidth(viewer)).toBe(true);
});
