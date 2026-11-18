import { expect, test } from '../dsl/fixtures';
import {
  check,
  historyReachedItsStart,
  isOnWatchList,
  nextEpisodeOf,
  openWatchList,
  scrollUpIntoHistory,
  sectionOf,
  showWatchedUpTo,
  takeOut,
  toggleView,
  watchedShows,
} from '../dsl/watch-list';

test.describe('Watch list', () => {
  test('shows the next episode of each show being watched, in a list or a grid kept on the device', async ({
    viewer,
    admin: { page },
  }) => {
    // Given a show watched up to its first episode
    const show = await showWatchedUpTo(viewer, 'Copper Lane', 1, 1);

    // When they open the watch list
    await openWatchList(viewer);

    // Then its card offers the second episode, with three more aired, under Watch next
    expect(await nextEpisodeOf(viewer, show)).toBe('S01|E02+3');
    await expect(viewer.app.card(show)).toContainText('Episode 2');
    expect(await sectionOf(viewer, show)).toBe('Watch next');

    // And the grid they switch to is still there when they come back
    expect(await toggleView(viewer)).toBe(true);
    await page.reload();
    await expect(viewer.app.card(show)).toBeVisible();
    expect(await viewer.app.isGrid()).toBe(true);
    expect(await toggleView(viewer)).toBe(false);
  });

  test('puts shows not watched for a month under their own heading', async ({ viewer, admin: { page } }) => {
    const card = {
      tmdb_id: 1,
      poster_path: null,
      season_number: 2,
      episode_number: 4,
      title: 'Later',
      airstamp: null,
      day: '2026-01-01',
      remaining: 0,
    };
    await page.route('/api/watch-list', (route) =>
      route.fulfill({
        json: {
          episodes: [
            { ...card, episode_id: 'a', show_title: 'Recent show', section: 'next', last_watched_at: null },
            { ...card, episode_id: 'b', show_title: 'Old show', section: 'dormant', last_watched_at: null },
          ],
        },
      }),
    );

    await openWatchList(viewer);

    expect(await sectionOf(viewer, 'Recent show')).toBe('Watch next');
    expect(await sectionOf(viewer, 'Old show')).toBe('Haven’t watched for a while');
  });

  test('one tap on the check moves the card to the next episode before the server answers', async ({
    viewer,
    admin: { page },
  }) => {
    // Given a show watched up to its first episode, and a server slow to answer
    const show = await showWatchedUpTo(viewer, 'Slow Answer', 1, 1);
    await openWatchList(viewer);
    let answer!: () => void;
    const answered = new Promise<void>((resolve) => (answer = resolve));
    await page.route('**/watched', async (route) => {
      await answered;
      await route.continue();
    });

    // When they tap the check
    await check(viewer, show);

    // Then the card already offers the third episode
    await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E03+2');
    answer();

    // And it is still there once the server has saved it
    await page.reload();
    expect(await nextEpisodeOf(viewer, show)).toBe('S01|E03+2');
  });

  test('a show up to date leaves the list once its last aired episode is checked', async ({ viewer }) => {
    const show = await showWatchedUpTo(viewer, 'Caught Up', 2, 1);
    await openWatchList(viewer);

    await check(viewer, show);

    await expect.poll(() => isOnWatchList(viewer, show)).toBe(false);
  });

  test.describe('when the server refuses', () => {
    test.use({ allowedConsoleErrors: [/status of 500/] });

    test('a check goes back, with a message', async ({ viewer, admin: { page } }) => {
      const show = await showWatchedUpTo(viewer, 'Refused Check', 1, 1);
      await openWatchList(viewer);
      await page.route('**/watched', (route) => route.fulfill({ status: 500, body: 'down' }));

      await check(viewer, show);

      await expect(viewer.app.snackBar()).toContainText('Your change could not be saved.');
      await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E02+3');
    });
  });

  test('swiping a card or its menu puts the show to watch later or stops it', async ({ viewer, admin: { page } }) => {
    // Given two shows being watched
    const later = await showWatchedUpTo(viewer, 'Set Aside', 1, 1);
    const stopped = await showWatchedUpTo(viewer, 'Given Up', 1, 1);
    await openWatchList(viewer);

    // When they take one out to watch later and stop the other
    await takeOut(viewer, page, later, 'Watch later');
    await takeOut(viewer, page, stopped, 'Stop watching');

    // Then both leave the list, also once loaded again
    await expect.poll(() => isOnWatchList(viewer, later)).toBe(false);
    await expect.poll(() => isOnWatchList(viewer, stopped)).toBe(false);
    await page.reload();
    await expect(viewer.app.watchList()).toBeVisible();
    expect(await isOnWatchList(viewer, later)).toBe(false);
    expect(await isOnWatchList(viewer, stopped)).toBe(false);
  });

  test('scrolling up from the top loads the watch history, 30 at a time, to its start', async ({
    viewer,
    admin: { page },
  }) => {
    // Given 35 episodes watched
    await watchedShows(viewer, 7);
    await openWatchList(viewer);

    // When they scroll up from the top, then further up
    const first = await scrollUpIntoHistory(viewer, page);
    // The page loaded above the screen did not move what they were looking at.
    await expect(viewer.app.watchList()).toBeInViewport();
    const second = await scrollUpIntoHistory(viewer, page);

    // Then the history came in pages of 30, down to its start
    expect([first, second]).toEqual([30, 35]);
    await expect.poll(() => historyReachedItsStart(viewer)).toBe(true);
  });
});
