import { expect } from '@playwright/test';
import { Viewer } from './fixtures';

/** What an episode's sheet says: its number and title, facts, synopsis, TMDB score and the user's watch. */
export interface EpisodeSheetText {
  title: string;
  facts: string;
  overview: string;
  score: string;
  watched: string;
}

/** Open an episode of the open show by tapping its row. */
export async function openEpisode(viewer: Viewer, season: number, episode: number): Promise<void> {
  await viewer.app.openEpisodeSheet(season, episode);
}

/** Open the episode on the watch list card of a show. */
export async function openWatchListEpisode(viewer: Viewer, show: string): Promise<void> {
  await viewer.app.openCardSheet(viewer.app.card(show));
}

export async function closeEpisode(viewer: Viewer): Promise<void> {
  await viewer.app.closeEpisodeSheet();
}

export async function episodeSheet(viewer: Viewer): Promise<EpisodeSheetText> {
  return {
    title: await viewer.app.textOf('sheet-title'),
    facts: await viewer.app.textOf('sheet-facts'),
    overview: await viewer.app.textOf('sheet-overview'),
    score: await viewer.app.textOf('sheet-tmdb-score'),
    watched: await viewer.app.textOf('sheet-watched'),
  };
}

/** Tap the sheet's check; returns its line about the watch as the screen shows it at once. */
export async function tapSheetCheck(viewer: Viewer): Promise<string> {
  const check = viewer.app.sheetCheck();
  const pressed = await check.getAttribute('aria-pressed');
  await check.click();
  await expect(check).toHaveAttribute('aria-pressed', pressed === 'true' ? 'false' : 'true');
  return viewer.app.textOf('sheet-watched');
}

/** Date the watch in the sheet, as "2025-03-14T20:30" in the user's time zone; returns the line once saved. */
export async function changeWatchDate(viewer: Viewer, local: string): Promise<string> {
  const saved = viewer.app.nextResponse('/watched');
  await viewer.app.setWatchDate(local);
  await saved;
  return viewer.app.textOf('sheet-watched');
}

/** Pick a watch date the app refuses; returns what it says and whether the field shows the saved date again. */
export async function refusedWatchDate(viewer: Viewer, local: string): Promise<{ message: string; kept: boolean }> {
  const saved = await viewer.app.watchDateShown();
  await viewer.app.setWatchDate(local);
  const message = (await viewer.app.snackBar().innerText()).trim();
  return { message, kept: (await viewer.app.watchDateShown()) === saved };
}

/** Today at `time` in the user's time zone, as a date-time field takes it: "2026-11-19T00:00". */
export async function todayAt(viewer: Viewer, time: string): Promise<string> {
  const timeZone = await viewer.api.timeZone();
  return `${new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date())}T${time}`;
}

/** Rate what the page or the sheet shows, with stars and a review, and wait until it is saved. */
export async function rate(viewer: Viewer, stars: number, review = ''): Promise<void> {
  await viewer.app.rate(stars, review);
}

export async function removeRating(viewer: Viewer): Promise<void> {
  await viewer.app.removeRating();
}

/** Use the Undo of the rating just removed, and wait until it is saved again. */
export async function undoRemoval(viewer: Viewer): Promise<void> {
  const saved = viewer.app.nextResponse('/rating');
  await viewer.app.snackBarAction('Undo');
  await saved;
}

export async function ratingShown(viewer: Viewer): Promise<{ stars: number; review: string }> {
  return viewer.app.ratingShown();
}

/** TMDB's score as the page says it, such as "8.3/10 from 1,234 votes on TMDB"; empty without one. */
export async function tmdbScore(viewer: Viewer): Promise<string> {
  const score = viewer.app.tmdbScoreLine();
  return (await score.count()) ? (await score.innerText()).trim() : '';
}
