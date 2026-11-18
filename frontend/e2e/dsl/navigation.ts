import { expect, Page } from '@playwright/test';
import { ApiDriver } from '../drivers/api.driver';
import { AppDriver } from '../drivers/app.driver';
import { ScreenDriver } from '../drivers/screen.driver';
import { uniqueTitle } from './tracking';

export interface Tab {
  name: string;
  height: number;
  /** Where the tab ends, from the top of the viewport. */
  bottom: number;
}

export async function tabs(page: Page): Promise<Tab[]> {
  const links = new AppDriver(page).tabLinks();
  const result: Tab[] = [];
  for (const link of await links.all()) {
    const box = (await link.boundingBox())!;
    result.push({ name: (await link.innerText()).trim(), height: box.height, bottom: box.y + box.height });
  }
  return result;
}

export async function activeTab(page: Page): Promise<string> {
  const current = new AppDriver(page).activeTab();
  await expect(current).toHaveCount(1);
  return (await current.innerText()).trim();
}

/** Open `address` as a bookmark, signed in. */
export async function openAddress(page: Page, address: string): Promise<void> {
  const app = new AppDriver(page);
  await app.openAddress(address);
  await expect(app.navigation()).toBeVisible();
}

/** The path and query the app shows. */
export function currentAddress(page: Page): string {
  return new AppDriver(page).address();
}

/** The browser tab's title. */
export async function pageTitle(page: Page): Promise<string> {
  return new AppDriver(page).title();
}

/** Open the app while the server cannot be reached; returns what the screen says. */
export async function openWhileServerUnreachable(page: Page): Promise<string> {
  const app = new AppDriver(page);
  await app.cutOffApi();
  await app.openAddress('/');
  return (await app.unreachable().innerText()).trim();
}

/** Each screen of the tabs, opened the way a user reaches it, with the title its browser tab shows. */
export async function openEveryScreen(
  page: Page,
): Promise<{ name: string; title: string; open: () => Promise<void> }[]> {
  const app = new AppDriver(page);
  const api = new ApiDriver(page);
  const showTitle = uniqueTitle('Every Screen');
  const show = await api.markWatched(showTitle, [[1, 1]]);
  const movieTitle = uniqueTitle('Every Screen');
  await api.addMovie(movieTitle);
  const movie = await api.findMovie(movieTitle);
  return [
    { name: 'Watch list', title: 'Watch list · MinTrack', open: () => app.openWatchList() },
    {
      name: 'Upcoming',
      title: 'Upcoming · MinTrack',
      open: async () => {
        await app.openUpcoming();
        // The show watched for the show page's screen airs its next episode within the four weeks.
        await expect(app.upcomingDays().first()).toBeVisible();
      },
    },
    {
      name: 'Discover',
      title: 'Discover · MinTrack',
      open: async () => {
        await app.openTab('Discover');
        await expect(app.trendingItems('Trending movies').first()).toBeVisible();
      },
    },
    {
      name: 'Show, with a season open',
      title: `${showTitle} · MinTrack`,
      open: async () => {
        await app.openShowPage(show);
        await app.openSeason(1);
        await expect(app.episode(1, 3)).toBeVisible();
      },
    },
    {
      name: 'Show, About',
      title: `${showTitle} · MinTrack`,
      open: async () => {
        await app.openShowPage(show);
        await app.openShowTab('About');
        await expect(app.showText('Channel Nine')).toBeVisible();
      },
    },
    { name: 'Movie', title: `${movieTitle} · MinTrack`, open: () => app.openMoviePage(movie) },
    {
      name: 'Profile',
      title: 'Profile · MinTrack',
      open: async () => {
        await app.openTab('Profile');
        await expect(app.logOutButton()).toBeVisible();
      },
    },
    { name: 'Shows', title: 'Collection · MinTrack', open: () => app.openLibrary('Shows') },
    {
      name: 'Admin',
      title: 'Admin · MinTrack',
      open: async () => {
        await app.openTab('Admin');
        await expect(app.adminUsers().first()).toBeVisible();
      },
    },
  ];
}

export async function fitsTheScreen(page: Page): Promise<boolean> {
  return new ScreenDriver(page).fitsWidth();
}

export async function smallTargets(page: Page): Promise<string[]> {
  return new ScreenDriver(page).smallTargets();
}

export async function accessibilityViolations(page: Page): Promise<string[]> {
  return new ScreenDriver(page).accessibilityViolations();
}
