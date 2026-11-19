import { expect, test } from '../dsl/fixtures';
import {
  check,
  finishedInHistory,
  finishedShow,
  firstCardOnScreen,
  historyReachedItsStart,
  isGrid,
  isOnWatchList,
  isSectionOpen,
  isStill,
  nextEpisodeOf,
  onWatchLaterShelf,
  openWatchList,
  refusingServer,
  reopenWatchList,
  scrollUpIntoHistory,
  sectionHeaders,
  sectionOf,
  serveWatchList,
  showWatchedUpTo,
  slowServer,
  takeOut,
  takeOutByKeyboard,
  toggleSection,
  toggleView,
  undo,
  watchedShows,
} from '../dsl/watch-list';

test.describe('Watch list', () => {
  test('shows the next episode of each show being watched, in a list or a grid kept on the device', async ({
    viewer,
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
    await toggleView(viewer);
    await expect.poll(() => isGrid(viewer)).toBe(true);
    await reopenWatchList(viewer);
    await expect.poll(() => isGrid(viewer)).toBe(true);
    await toggleView(viewer);
    await expect.poll(() => isGrid(viewer)).toBe(false);
  });

  test.describe('with shows in every section', () => {
    test.beforeEach(async ({ viewer }) => {
      const card = {
        tmdb_id: 1,
        poster_path: null,
        season_number: 2,
        episode_number: 4,
        title: 'Later',
        airstamp: null,
        day: '2026-01-01',
        remaining: 0,
        last_watched_at: null,
      };
      await serveWatchList(viewer, {
        episodes: [
          { ...card, episode_id: 'a', show_title: 'Recent show', section: 'next' },
          { ...card, tmdb_id: 2, episode_id: 'b', show_title: 'Second show', section: 'next' },
          { ...card, tmdb_id: 3, episode_id: 'c', show_title: 'Old show', section: 'dormant' },
          { ...card, tmdb_id: 4, episode_id: 'd', show_title: 'New show', section: 'not_started' },
        ],
      });
    });

    test('puts shows watched lately, not for a while and not started under their own counted headings', async ({
      viewer,
    }) => {
      await openWatchList(viewer);

      expect(await sectionOf(viewer, 'Recent show')).toBe('Watch next');
      expect(await sectionOf(viewer, 'Old show')).toBe('Haven’t watched for a while');
      expect(await sectionOf(viewer, 'New show')).toBe('Haven’t started');
      expect(await sectionHeaders(viewer)).toEqual([
        'Watch next 2',
        'Haven’t watched for a while 1',
        'Haven’t started 1',
      ]);
    });

    test('a section folds from its heading and stays folded on the device', async ({ viewer }) => {
      await openWatchList(viewer);

      await toggleSection(viewer, 'Watch next');
      await expect.poll(() => isOnWatchList(viewer, 'Recent show')).toBe(false);

      await reopenWatchList(viewer);
      await expect.poll(() => isOnWatchList(viewer, 'Old show')).toBe(true);
      expect(await isSectionOpen(viewer, 'Watch next')).toBe(false);
      expect(await isOnWatchList(viewer, 'Recent show')).toBe(false);

      await toggleSection(viewer, 'Watch next');
      await expect.poll(() => isOnWatchList(viewer, 'Recent show')).toBe(true);
    });
  });

  test('a long watch list comes to rest once its cards are in, leaving no animation in effect', async ({ viewer }) => {
    // Given a watch list of 60 shows
    await serveWatchList(viewer, {
      episodes: Array.from({ length: 60 }, (_, index) => ({
        tmdb_id: index + 1,
        episode_id: `e${index}`,
        show_title: `Show ${index}`,
        poster_path: null,
        season_number: 1,
        episode_number: 2,
        title: 'Next',
        airstamp: null,
        day: '2026-01-01',
        remaining: 0,
        last_watched_at: null,
        section: 'next',
      })),
    });

    // When they open it
    await openWatchList(viewer);
    expect(await sectionHeaders(viewer)).toEqual(['Watch next 60']);

    // Then once the cards have risen in, no animation keeps running or holding its end state
    await expect.poll(() => isStill(viewer)).toBe(true);
  });

  test('one tap on the check moves the card to the next episode before the server answers', async ({ viewer }) => {
    // Given a show watched up to its first episode, and a server slow to answer
    const show = await showWatchedUpTo(viewer, 'Slow Answer', 1, 1);
    await openWatchList(viewer);
    const answer = await slowServer(viewer);

    // When they tap the check
    await check(viewer, show);

    // Then the card already offers the third episode
    await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E03+2');
    await answer();

    // And it is still there once the server has saved it
    await reopenWatchList(viewer);
    await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E03+2');
  });

  test('a check says which episode was watched, and Undo brings its card back', async ({ viewer }) => {
    // Given a show watched up to its first episode
    const show = await showWatchedUpTo(viewer, 'Second Guess', 1, 1);
    await openWatchList(viewer);

    // When they check its card, then use Undo
    await check(viewer, show);
    await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E03+2');
    const message = await undo(viewer);

    // Then the card offers the second episode again, also once loaded again
    expect(message).toContain('S01E02 watched');
    await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E02+3');
    await reopenWatchList(viewer);
    await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E02+3');
  });

  test('a show up to date leaves the list once its last aired episode is checked', async ({ viewer }) => {
    const show = await showWatchedUpTo(viewer, 'Caught Up', 2, 1);
    await openWatchList(viewer);

    await check(viewer, show);

    await expect.poll(() => isOnWatchList(viewer, show)).toBe(false);
  });

  test.describe('when the server refuses', () => {
    test.use({ allowedConsoleErrors: [/status of 500/] });

    test('a check goes back, with a message', async ({ viewer }) => {
      const show = await showWatchedUpTo(viewer, 'Refused Check', 1, 1);
      await openWatchList(viewer);
      await refusingServer(viewer);

      await check(viewer, show);

      await expect(viewer.app.snackBar()).toContainText('Your change could not be saved.');
      await expect.poll(() => nextEpisodeOf(viewer, show)).toBe('S01|E02+3');
    });
  });

  test('swiping a card or its menu puts the show to watch later or stops it', async ({ viewer }) => {
    // Given two shows being watched
    const later = await showWatchedUpTo(viewer, 'Set Aside', 1, 1);
    const stopped = await showWatchedUpTo(viewer, 'Given Up', 1, 1);
    await openWatchList(viewer);

    // When they take one out to watch later and stop the other
    await takeOut(viewer, later, 'Watch later');
    await takeOut(viewer, stopped, 'Stop watching');

    // Then both leave the list, also once loaded again
    await expect.poll(() => isOnWatchList(viewer, later)).toBe(false);
    await expect.poll(() => isOnWatchList(viewer, stopped)).toBe(false);
    await reopenWatchList(viewer);
    await expect.poll(() => isOnWatchList(viewer, later)).toBe(false);
    await expect.poll(() => isOnWatchList(viewer, stopped)).toBe(false);
  });

  test('Watch later says where the show went, can be undone, and the show waits on Profile', async ({ viewer }) => {
    // Given two shows being watched
    const kept = await showWatchedUpTo(viewer, 'Second Thoughts', 1, 1);
    const later = await showWatchedUpTo(viewer, 'Rainy Day', 1, 1);
    await openWatchList(viewer);

    // When one is put to watch later then brought back with Undo
    await takeOut(viewer, kept, 'Watch later');
    expect(await undo(viewer)).toContain('Moved to Watch later');

    // Then it is on the list again, also once loaded again
    await expect.poll(() => isOnWatchList(viewer, kept)).toBe(true);
    await reopenWatchList(viewer);
    await expect.poll(() => isOnWatchList(viewer, kept)).toBe(true);

    // And the other one, put to watch later, waits in Profile's Watch later row
    await takeOut(viewer, later, 'Watch later');
    await expect.poll(() => isOnWatchList(viewer, later)).toBe(false);
    expect(await onWatchLaterShelf(viewer, later)).toBe(true);
  });

  test('a card’s menu works with the keyboard alone, with a visible focus ring', async ({ viewer }) => {
    const show = await showWatchedUpTo(viewer, 'Keyboard Only', 1, 1);
    await openWatchList(viewer);

    const ringShown = await takeOutByKeyboard(viewer, show, 'Stop watching');

    expect(ringShown).toBe(true);
    await expect.poll(() => isOnWatchList(viewer, show)).toBe(false);
  });

  test('scrolling up from the top loads the watch history, 30 at a time, to its start', async ({ viewer }) => {
    // Given 36 episodes watched, one show still on the watch list
    await showWatchedUpTo(viewer, 'On Screen', 1, 1);
    await watchedShows(viewer, 7);
    await openWatchList(viewer);

    // When they scroll up from the top, then further up
    const first = await scrollUpIntoHistory(viewer);
    // The page loaded above the screen did not move what they were looking at.
    expect(await firstCardOnScreen(viewer)).toBe(true);
    const second = await scrollUpIntoHistory(viewer);

    // Then the history came in pages of 30, down to its start
    expect([first, second]).toEqual([30, 36]);
    await expect.poll(() => historyReachedItsStart(viewer)).toBe(true);
  });

  test('the history puts the Finished badge on the episodes of finished shows', async ({ viewer }) => {
    // Given a show watched to its end, and one still being watched
    const finished = await finishedShow(viewer, 'Last Light');
    const watching = await showWatchedUpTo(viewer, 'Still Going', 1, 1);
    await openWatchList(viewer);

    // When they scroll up into the history
    await scrollUpIntoHistory(viewer);

    // Then only the finished show's episodes carry the badge
    await expect.poll(() => finishedInHistory(viewer, finished)).toBe(true);
    await expect.poll(() => finishedInHistory(viewer, watching)).toBe(false);
  });
});
