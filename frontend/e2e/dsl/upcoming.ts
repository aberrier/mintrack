import { expect } from '@playwright/test';
import { Viewer } from './fixtures';

/** Open Episodes, then its Upcoming sub-tab; returns whether the sub-tab says it is the current page. */
export async function openUpcoming(viewer: Viewer): Promise<boolean> {
  await viewer.app.openUpcoming();
  return expect(viewer.app.episodesTab('Upcoming'))
    .toHaveAttribute('aria-current', 'page')
    .then(
      () => true,
      () => false,
    );
}

/** The upcoming episodes the server sends, replaced by `response`, for a state the scenario does not build. */
export async function serveUpcoming(viewer: Viewer, response: object): Promise<void> {
  await viewer.app.serveUpcoming(response);
}

/** What the open list says when it has nothing to show. */
export async function emptyMessage(viewer: Viewer): Promise<string> {
  await expect(viewer.app.emptyState()).toBeVisible();
  return (await viewer.app.emptyState().innerText()).trim();
}

/** The month names shown where a new month starts. */
export async function months(viewer: Viewer): Promise<string[]> {
  await expect(viewer.app.upcomingDays().first()).toBeVisible();
  return (await viewer.app.upcomingMonths().allInnerTexts()).map((text) => text.trim());
}

/** The heading of the day under which the show's episode airs, such as "Today", "Friday" or "24 November". */
export async function dayOf(viewer: Viewer, show: string): Promise<string> {
  const day = viewer.app.upcomingDays().filter({ hasText: show });
  await expect(day).toBeVisible();
  // The text as written, not as styled (the heading shows in capitals).
  return (await day.getByRole('heading').first().textContent())!.trim();
}

/** The episode code and air time of the show's episode under a day. */
export async function episodeOn(viewer: Viewer, day: string, show: string): Promise<{ code: string; time: string }> {
  const region = viewer.app.upcomingDay(day);
  await expect(region).toContainText(show);
  const time = viewer.app.upcomingEpisodeDetail(region);
  return {
    code: (await region.getByTestId('episode-code').first().innerText()).replace(/\s+/g, ''),
    time: (await time.count()) ? (await time.first().innerText()).trim() : '',
  };
}

/** Whether the grid shows a poster named after the whole episode, such as "Show, season 1 episode 2, Title". */
export async function posterShown(viewer: Viewer, day: string, name: string): Promise<boolean> {
  return expect(viewer.app.upcomingEpisode(viewer.app.upcomingDay(day), name))
    .toBeVisible()
    .then(
      () => true,
      () => false,
    );
}

/** Whether nothing overflows the screen sideways. */
export async function fitsTheWidth(viewer: Viewer): Promise<boolean> {
  return viewer.app.fitsWidth();
}

/** Switch the list between rows and a grid. */
export async function toggleView(viewer: Viewer): Promise<void> {
  await viewer.app.toggleView();
}
