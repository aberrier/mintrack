import { expect, test } from '../dsl/fixtures';

test('someone following no show is told what Up next and Upcoming will show', async ({ admin: { page } }) => {
  await page.getByRole('link', { name: 'Up next' }).click();
  await expect(page.getByRole('heading', { name: 'Up next', level: 1 })).toBeVisible();
  await expect(page.getByTestId('empty')).toContainText('Nothing to watch next');

  await page.getByRole('link', { name: 'Upcoming' }).click();
  await expect(page.getByRole('link', { name: 'Upcoming' })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('empty')).toContainText('Nothing airs in the next four weeks');
});

test('upcoming episodes fit the screen, grouped by day', async ({ admin: { page } }) => {
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

  await page.goto('/upcoming');

  await expect(page.getByRole('region', { name: 'New episodes' })).toContainText('Missed show');
  const day = page.getByRole('region', { name: 'Friday, January 2' });
  await expect(day).toContainText('Next show');
  await expect(day.getByTestId('episode-detail')).toHaveText(/8:00\s?PM/);
  const viewport = page.viewportSize()!;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
});
