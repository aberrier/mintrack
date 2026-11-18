import type { Page } from '@playwright/test';
import { Navigation } from '../drivers/pages';
import { expect, test } from '../dsl/fixtures';

const YAMTRACK_EXPORT = [
  'media_id,source,media_type,title,image,season_number,episode_number,score,progress,status,start_date,end_date,notes,progressed_at',
  '1942,igdb,game,Some Game,,,,,,Completed,,,,',
].join('\n');

const job = (changes: object) => ({
  id: 'job-1',
  source: 'yamtrack',
  status: 'pending',
  filename: 'yamtrack.csv',
  total: 0,
  processed: 0,
  report: null,
  created_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  ...changes,
});

/** The import API as the server answers it: no import yet, then the uploaded job's states, one per read. */
async function serveImports(page: Page, states: object[]): Promise<{ uploads: string[] }> {
  const uploads: string[] = [];
  let latest: object | null = null;
  await page.route('/api/imports/latest', (route) => {
    if (latest !== null && states.length) latest = states.shift()!;
    return route.fulfill({ json: latest });
  });
  await page.route('/api/imports', (route) => {
    uploads.push(route.request().postData() ?? '');
    latest = states.shift()!;
    return route.fulfill({ status: 202, json: latest });
  });
  return { uploads };
}

test('someone imports a Yamtrack export from their profile and reads the report', async ({ admin: { page } }) => {
  const api = await serveImports(page, [
    job({ status: 'pending' }),
    job({ status: 'running', total: 2, processed: 1 }),
    job({
      status: 'done',
      total: 2,
      processed: 2,
      report: {
        imported: 1,
        already_present: 0,
        unmatched_count: 1,
        unmatched: [{ title: 'Some Game', reason: 'unsupported' }],
      },
    }),
  ]);
  await new Navigation(page).openProfile();

  await page.getByTestId('import-file').setInputFiles({
    name: 'yamtrack.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(YAMTRACK_EXPORT),
  });

  await expect(page.getByTestId('import-status')).toContainText('Importing… 1 / 2');
  const report = page.getByTestId('import-report');
  await expect(report).toContainText('Added1');
  await expect(page.getByText('Some Game: not a movie or show on TMDB')).toBeVisible();
  expect(api.uploads[0]).toContain('name="source"\r\n\r\nyamtrack');
  expect(api.uploads[0]).toContain('filename="yamtrack.csv"');
});

test('someone choosing TV Time sees which export files to upload', async ({ admin: { page } }) => {
  await serveImports(page, []);
  await new Navigation(page).openProfile();

  await page.getByRole('radio', { name: 'TV Time' }).click();

  await expect(page.getByText('tracking-prod-records-v2.csv')).toBeVisible();
  for (const target of [
    page.getByRole('radio', { name: 'TV Time' }),
    page.getByRole('button', { name: 'Choose a file and import' }),
  ]) {
    expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(48);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()!.width,
  );
});
