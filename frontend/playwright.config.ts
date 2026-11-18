import { defineConfig, devices } from '@playwright/test';

/**
 * Browser tests against a running MinTrack (the backend serving the built app).
 * Chromium only: it treats localhost as a secure origin for cookies and service workers; WebKit does not.
 */
export default defineConfig({
  testDir: './e2e/specs',
  fullyParallel: true,
  forbidOnly: !!process.env['CI'],
  retries: 0,
  // Locally a broken change fails fast: shorter waits and a stop after five failures; CI keeps the defaults.
  ...(process.env['CI'] ? {} : { timeout: 20_000, expect: { timeout: 3_000 }, maxFailures: 5 }),
  // Locally, `dot` prints one character per test, then the failures; pass `--reporter=list` to see every test.
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'dot',
  use: {
    baseURL: process.env['MINTRACK_E2E_BASE_URL'] ?? 'http://localhost:8000',
    // Recording costs every test; locally, rerun a failure with `--trace on` to get one.
    trace: process.env['CI'] ? 'retain-on-failure' : 'off',
    // page.route() does not see requests a service worker sends; the PWA spec allows it.
    serviceWorkers: 'block',
  },
  projects: [
    { name: 'phone', use: { ...devices['Pixel 7'] } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  ],
});
