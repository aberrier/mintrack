import { ImportsSection, Navigation } from '../drivers/pages';
import { ScreenDriver } from '../drivers/screen.driver';
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

test('someone imports a Yamtrack export from their profile and reads the report', async ({ admin: { page } }) => {
  const imports = new ImportsSection(page);
  const api = await imports.serveImports([
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
  await new Navigation(page).openSettings();

  await imports.upload({
    name: 'yamtrack.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(YAMTRACK_EXPORT),
  });

  await expect(imports.status()).toContainText('Importing… 1 / 2');
  await expect(imports.report()).toContainText('Added1');
  // What was not imported waits folded under its count, listed once opened.
  await expect(imports.warnings()).toHaveText('Warnings (1)');
  await expect(imports.line('Some Game: not a movie or show on TMDB')).toBeHidden();
  await imports.warnings().click();
  await expect(imports.line('Some Game: not a movie or show on TMDB')).toBeVisible();
  expect(api.uploads[0]).toContain('name="source"\r\n\r\nyamtrack');
  expect(api.uploads[0]).toContain('filename="yamtrack.csv"');
});

test('someone choosing TV Time sees which export files to upload', async ({ admin: { page } }) => {
  const imports = new ImportsSection(page);
  await imports.serveImports([]);
  await new Navigation(page).openSettings();

  await imports.chooseSource('TV Time');

  await expect(imports.line('tracking-prod-records-v2.csv')).toBeVisible();
  for (const target of [imports.source('TV Time'), imports.chooseFile()]) {
    expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(48);
  }
  expect(await new ScreenDriver(page).fitsWidth()).toBe(true);
});
