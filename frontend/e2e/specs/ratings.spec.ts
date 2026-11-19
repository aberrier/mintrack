import { expect, test } from '../dsl/fixtures';
import {
  changeWatchDate,
  closeEpisode,
  episodeSheet,
  openEpisode,
  openWatchListEpisode,
  rate,
  ratingShown,
  refusedWatchDate,
  removeRating,
  tapSheetCheck,
  tmdbScore,
  todayAt,
  undoRemoval,
} from '../dsl/ratings';
import { openMovie, openShow, seedShows, today, uniqueTitle } from '../dsl/tracking';
import { nextEpisodeOf, openWatchList } from '../dsl/watch-list';

test('someone opens an episode from its show, marks it, dates the watch and rates it', async ({ viewer }) => {
  // Given a show found by searching
  const title = uniqueTitle('Harbour Lights');
  await openShow(viewer, title);

  // When they tap an episode, its sheet tells what it is
  await openEpisode(viewer, 1, 2);
  const sheet = await episodeSheet(viewer);
  expect(sheet.title).toBe('S01E02 Episode 2');
  expect(sheet.facts).toMatch(/^Aired .+ · Channel Nine$/);
  expect(sheet.overview).toBe('What happens in episode 2.');
  expect(sheet.score).toBe('7.5/10 from 24 votes on TMDB');
  expect(sheet.watched).toBe('Not watched');

  // When they mark it there, it is watched today
  expect(await tapSheetCheck(viewer)).toMatch(new RegExp(`^Watched ${await today(viewer)}, \\d{1,2}:\\d\\d$`));

  // When they pick a time before the episode aired, the sheet refuses it and keeps the date saved
  expect(await refusedWatchDate(viewer, '2000-01-01T20:30')).toEqual({
    message: 'Pick a time after the episode aired.',
    kept: true,
  });

  // When they say they watched it earlier today, the sheet says so
  const watched = `Watched ${await today(viewer)}, 0:00`;
  expect(await changeWatchDate(viewer, await todayAt(viewer, '00:00'))).toBe(watched);

  // When they rate it with a review, the sheet shows it again the next time
  await rate(viewer, 4, 'The twist works.');
  await closeEpisode(viewer);
  await openEpisode(viewer, 1, 2);
  expect(await ratingShown(viewer)).toEqual({ stars: 4, review: 'The twist works.' });
  expect((await episodeSheet(viewer)).watched).toBe(watched);

  // When they remove the rating, then rate again while its Undo shows, the new rating stays
  await removeRating(viewer);
  await rate(viewer, 2);
  await closeEpisode(viewer);
  await openEpisode(viewer, 1, 2);
  expect(await ratingShown(viewer)).toEqual({ stars: 2, review: '' });
});

test('marking the episode of a watch list card from its sheet moves the card on', async ({ viewer }) => {
  // Given a show added but not started
  const title = uniqueTitle('Copper Valley');
  await seedShows(viewer, [title]);
  await openWatchList(viewer);
  expect(await nextEpisodeOf(viewer, title)).toMatch(/^S01\|E01/);

  // When they open its card's episode and mark it
  await openWatchListEpisode(viewer, title);
  await tapSheetCheck(viewer);
  await closeEpisode(viewer);

  // Then the card offers the following episode
  await expect.poll(() => nextEpisodeOf(viewer, title)).toMatch(/^S01\|E02/);
});

test('someone rates a show, then changes their mind', async ({ viewer }) => {
  // Given a show, whose About tab gives TMDB's score
  await openShow(viewer, uniqueTitle('Tidal Lines'));
  await viewer.app.openShowTab('About');
  expect(await tmdbScore(viewer)).toBe('8.3/10 from 1,234 votes on TMDB');

  // When they rate it, then change the stars, the page keeps the latest after a reload
  await rate(viewer, 2);
  await rate(viewer, 5, 'Grew on me.');
  await viewer.app.reload();
  expect(await ratingShown(viewer)).toEqual({ stars: 5, review: 'Grew on me.' });
});

test('someone rates a movie, then removes the rating', async ({ viewer }) => {
  // Given a movie nobody voted for on TMDB, rated
  await openMovie(viewer, uniqueTitle('Glass Orchard'));
  expect(await tmdbScore(viewer)).toBe('');
  await rate(viewer, 3, 'Pretty.');

  // When they remove the rating, Undo brings it back
  await removeRating(viewer);
  await undoRemoval(viewer);
  await expect.poll(() => ratingShown(viewer)).toEqual({ stars: 3, review: 'Pretty.' });

  // When they remove it again, it stays removed
  await removeRating(viewer);
  await viewer.app.reload();
  expect(await ratingShown(viewer)).toEqual({ stars: 0, review: '' });
});
