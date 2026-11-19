import { expect, test } from '../dsl/fixtures';
import {
  changeWatchDate,
  closeEpisode,
  episodeSheet,
  openEpisode,
  openWatchListEpisode,
  rate,
  ratingShown,
  removeRating,
  tapSheetCheck,
  tmdbScore,
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
  expect(sheet.score).toBe('7.5 · TMDB (24)');
  expect(sheet.watched).toBe('Not watched');

  // When they mark it there, it is watched today
  expect(await tapSheetCheck(viewer)).toMatch(new RegExp(`^Watched ${await today(viewer)}, \\d\\d:\\d\\d$`));

  // When they say they watched it on another day, the sheet says so
  expect(await changeWatchDate(viewer, '2025-03-14T20:30')).toBe('Watched 14 Mar 2025, 20:30');

  // When they rate it with a review, the sheet shows it again the next time
  await rate(viewer, 4, 'The twist works.');
  await closeEpisode(viewer);
  await openEpisode(viewer, 1, 2);
  expect(await ratingShown(viewer)).toEqual({ stars: 4, review: 'The twist works.' });
  expect((await episodeSheet(viewer)).watched).toBe('Watched 14 Mar 2025, 20:30');
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

test('someone rates a show and a movie, changes their mind and removes a rating', async ({ viewer }) => {
  // Given a show, whose About tab gives TMDB's score
  await openShow(viewer, uniqueTitle('Tidal Lines'));
  await viewer.app.openShowTab('About');
  expect(await tmdbScore(viewer)).toBe('8.3/10 from 1,234 votes on TMDB');

  // When they rate it, then change the stars, the page keeps the latest after a reload
  await rate(viewer, 2);
  await rate(viewer, 5, 'Grew on me.');
  await viewer.app.reload();
  expect(await ratingShown(viewer)).toEqual({ stars: 5, review: 'Grew on me.' });

  // Given a movie nobody voted for on TMDB, rated and then unrated
  await openMovie(viewer, uniqueTitle('Glass Orchard'));
  expect(await tmdbScore(viewer)).toBe('');
  await rate(viewer, 3);
  await removeRating(viewer);
  await viewer.app.reload();
  expect(await ratingShown(viewer)).toEqual({ stars: 0, review: '' });
});
