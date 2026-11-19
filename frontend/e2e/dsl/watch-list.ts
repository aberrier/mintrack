import { expect } from '@playwright/test';
import { Viewer } from './fixtures';
import { uniqueTitle } from './tracking';

/** The fake TMDB's shows: season 1 has three aired episodes, season 2 two aired and one in a week. */
const AIRED: [number, number][] = [
  [1, 1],
  [1, 2],
  [1, 3],
  [2, 1],
  [2, 2],
];

/** A show the viewer watched up to `season`x`episode` (in airing order), under a title no other test uses. */
export async function showWatchedUpTo(viewer: Viewer, base: string, season: number, episode: number): Promise<string> {
  const title = uniqueTitle(base);
  const upTo = AIRED.findIndex(([s, e]) => s === season && e === episode);
  await viewer.api.markWatched(title, AIRED.slice(0, upTo + 1));
  return title;
}

/** An ended show the viewer watched to its end, under a title no other test uses. */
export async function finishedShow(viewer: Viewer, base: string): Promise<string> {
  const title = uniqueTitle(base, { ended: true });
  await viewer.api.markWatched(title, [...AIRED, [2, 3]]);
  return title;
}

/** Shows entirely watched, for a history of `count` × 5 episodes. */
export async function watchedShows(viewer: Viewer, count: number): Promise<void> {
  for (let index = 0; index < count; index++) await viewer.api.markWatched(uniqueTitle(`History ${index}`), AIRED);
}

export async function openWatchList(viewer: Viewer): Promise<void> {
  await viewer.app.openWatchList();
}

/** The episode a show's card offers next, such as "S01 | E02+3" (three more aired after it). */
export async function nextEpisodeOf(viewer: Viewer, show: string): Promise<string> {
  await expect(viewer.app.card(show)).toBeVisible();
  return viewer.app.cardEpisode(show);
}

/** The title of the section holding the show's card, such as "Watch next". */
export async function sectionOf(viewer: Viewer, show: string): Promise<string> {
  return viewer.app.cardSection(show);
}

/** The watch list as the server would send it, for a state the scenario does not build. */
export async function serveWatchList(viewer: Viewer, response: object): Promise<void> {
  await viewer.app.serveWatchList(response);
}

/** Take a show out through its card's menu with the keyboard only; returns whether its focus ring showed. */
export async function takeOutByKeyboard(viewer: Viewer, show: string, action: 'Watch later' | 'Stop watching') {
  return viewer.app.cardActionByKeyboard(show, action);
}

/** The snackbar's message once a show is taken out, then its Undo used. */
export async function undo(viewer: Viewer): Promise<string> {
  const message = (await viewer.app.snackBar().innerText()).trim();
  await viewer.app.snackBarAction('Undo');
  return message;
}

/** Whether the Profile tab's Watch later row holds the show. */
export async function onWatchLaterShelf(viewer: Viewer, show: string): Promise<boolean> {
  await viewer.app.openTab('Profile');
  return expect(viewer.app.profileItem('Watch later', show))
    .toBeVisible()
    .then(
      () => true,
      () => false,
    );
}

export async function check(viewer: Viewer, show: string): Promise<void> {
  await viewer.app.checkCard(show);
}

/** The watch list's section headings with their counts, such as "Watch next 2", in order. */
export async function sectionHeaders(viewer: Viewer): Promise<string[]> {
  await expect(viewer.app.sectionToggles().first()).toBeVisible();
  // The text as written, not as styled (the headings show in capitals): the title, then the count.
  return viewer.app.sectionToggles().evaluateAll((toggles) =>
    toggles.map((toggle) =>
      [...toggle.children]
        .map((part) => part.textContent?.trim())
        .filter(Boolean)
        .join(' '),
    ),
  );
}

/** Fold or unfold a section of the watch list from its heading. */
export async function toggleSection(viewer: Viewer, name: string): Promise<void> {
  await viewer.app.sectionToggle(name).click();
}

export async function isSectionOpen(viewer: Viewer, name: string): Promise<boolean> {
  return (await viewer.app.sectionToggle(name).getAttribute('aria-expanded')) === 'true';
}

export async function isOnWatchList(viewer: Viewer, show: string): Promise<boolean> {
  return (await viewer.app.card(show).count()) > 0;
}

/** Load the watch list again, as when coming back later. */
export async function reopenWatchList(viewer: Viewer): Promise<void> {
  await viewer.app.reloadWatchList();
}

/**
 * A server that holds the next writes of watched episodes until the returned function is called, which resolves once
 * the server answered.
 */
export async function slowServer(viewer: Viewer): Promise<() => Promise<void>> {
  let release!: () => void;
  await viewer.app.holdRequests('/watched', new Promise<void>((resolve) => (release = resolve)));
  return async () => {
    const answered = viewer.app.nextResponse('/watched');
    release();
    await answered;
  };
}

/** A server that refuses to save watched episodes. */
export async function refusingServer(viewer: Viewer): Promise<void> {
  await viewer.app.failRequests('/watched');
}

/** Whether the screen is still: no animation runs or holds its end state on the page. */
export async function isStill(viewer: Viewer): Promise<boolean> {
  return (await viewer.app.animationsInEffect()) === 0;
}

/** Whether the first card of the watch list is on screen. */
export async function firstCardOnScreen(viewer: Viewer): Promise<boolean> {
  return expect(viewer.app.cards().first())
    .toBeInViewport()
    .then(
      () => true,
      () => false,
    );
}

/** Take a show out of the watch list the way a phone user does (swipe) or a desktop user does (menu). */
export async function takeOut(viewer: Viewer, show: string, action: 'Watch later' | 'Stop watching'): Promise<void> {
  await viewer.app.cardAction(show, action, (await viewer.app.isTouch()) ? 'swipe' : 'menu');
}

/** Switch list and grid. */
export async function toggleView(viewer: Viewer): Promise<void> {
  await viewer.app.toggleView();
}

/** Whether the watch list shows a grid of posters rather than rows. */
export async function isGrid(viewer: Viewer): Promise<boolean> {
  return viewer.app.isGrid();
}

/** Scroll up past the top of the watch list, and wait for the history page it loads. */
export async function scrollUpIntoHistory(viewer: Viewer): Promise<number> {
  const before = await viewer.app.historyEntries().count();
  if (before === 0) await viewer.app.scrollUpFromTop(await viewer.app.isTouch());
  else await viewer.app.scrollToTop();
  await expect(viewer.app.historyEntries()).not.toHaveCount(before);
  return viewer.app.historyEntries().count();
}

/** Whether the history's entries of the show carry the Finished badge on their poster. */
export async function finishedInHistory(viewer: Viewer, show: string): Promise<boolean> {
  const entry = viewer.app.historyEntry(show).first();
  // The badge renders with the entry's poster.
  await expect(entry).toBeVisible();
  return (await viewer.app.finishedBadge(entry).count()) > 0;
}

export async function historyReachedItsStart(viewer: Viewer): Promise<boolean> {
  return viewer.app.historyStart().isVisible();
}
