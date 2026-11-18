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
  const links = new AppDriver(page).navigation().getByRole('link');
  const result: Tab[] = [];
  for (const link of await links.all()) {
    const box = (await link.boundingBox())!;
    result.push({ name: (await link.innerText()).trim(), height: box.height, bottom: box.y + box.height });
  }
  return result;
}

export async function activeTab(page: Page): Promise<string> {
  const current = new AppDriver(page).navigation().locator('[aria-current="page"]');
  await expect(current).toHaveCount(1);
  return (await current.innerText()).trim();
}

/** The path and query the app shows after opening `address` as a bookmark. */
export async function addressAfterOpening(page: Page, address: string): Promise<string> {
  await page.goto(address);
  await expect(new AppDriver(page).navigation()).toBeVisible();
  await page.waitForLoadState('networkidle');
  const url = new URL(page.url());
  return url.pathname + url.search;
}

/** Each screen of the three tabs, opened the way a user reaches it. */
export async function openEveryScreen(page: Page): Promise<{ name: string; open: () => Promise<void> }[]> {
  const app = new AppDriver(page);
  const api = new ApiDriver(page);
  const show = await api.markWatched(uniqueTitle('Every Screen'), [[1, 1]]);
  const movieTitle = uniqueTitle('Every Screen');
  await api.addMovie(movieTitle);
  const movie = await api.findMovie(movieTitle);
  return [
    { name: 'Watch list', open: () => app.openWatchList() },
    {
      name: 'Upcoming',
      open: async () => {
        await app.openUpcoming();
        // The show watched for the show page's screen airs its next episode within the four weeks.
        await expect(page.getByRole('region', { name: /^\w+day, / }).first()).toBeVisible();
      },
    },
    {
      name: 'Discover',
      open: async () => {
        await app.openTab('Discover');
        await expect(app.trendingRow('Trending movies').getByTestId('trending-item').first()).toBeVisible();
      },
    },
    {
      name: 'Show, with a season open',
      open: async () => {
        await app.openShowPage(show);
        await app.openSeason(1);
        await expect(app.episode(1, 3)).toBeVisible();
      },
    },
    {
      name: 'Show, About',
      open: async () => {
        await app.openShowTab('About');
        await expect(page.getByText('Channel Nine').last()).toBeVisible();
      },
    },
    { name: 'Movie', open: () => app.openMoviePage(movie) },
    {
      name: 'Profile',
      open: async () => {
        await app.openTab('Profile');
        await expect(page.getByRole('button', { name: 'Log out', exact: true })).toBeVisible();
      },
    },
    { name: 'Shows', open: () => app.openLibrary('Shows') },
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
