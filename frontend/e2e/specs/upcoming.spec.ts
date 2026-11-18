import { expect, test } from '../dsl/fixtures';

test('someone following no show is told what Watch list and Upcoming will show', async ({
  viewer,
  admin: { page },
}) => {
  await viewer.app.openWatchList();
  await expect(page.getByTestId('empty')).toContainText('Nothing to watch next');

  await viewer.app.openUpcoming();
  await expect(viewer.app.episodesTabs().getByRole('link', { name: 'Upcoming' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByTestId('empty')).toContainText('Nothing airs in the next four weeks');
});

test('upcoming episodes fit the screen, grouped by day, in a list or a grid', async ({ viewer, admin: { page } }) => {
  const episode = {
    tmdb_id: 1,
    poster_path: null,
    season_number: 1,
    episode_number: 2,
    title: 'An episode title long enough to be cut on a phone screen without any horizontal scrolling',
    airstamp: '2099-01-02T20:00:00Z',
    day: '2099-01-02',
  };
  await page.route('/api/upcoming', (route) =>
    route.fulfill({
      json: {
        time_zone: 'UTC',
        new: [{ ...episode, episode_id: 'missed', show_title: 'Missed show', airstamp: null, day: '2098-12-30' }],
        days: [{ day: '2099-01-02', episodes: [{ ...episode, episode_id: 'next', show_title: 'Next show' }] }],
      },
    }),
  );

  await viewer.app.openUpcoming();

  await expect(page.getByRole('region', { name: 'New episodes' })).toContainText('Missed show');
  const day = page.getByRole('region', { name: 'Friday, January 2' });
  await expect(day).toContainText('Next show');
  await expect(day.getByTestId('episode-detail')).toHaveText(/8:00\s?PM/);
  const viewport = page.viewportSize()!;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);

  await viewer.app.viewToggle().click();
  await expect(day.getByRole('link', { name: 'Next show, S01 | E02, An episode title' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
});
