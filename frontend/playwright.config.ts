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
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env['MINTRACK_E2E_BASE_URL'] ?? 'http://localhost:8000',
    trace: 'retain-on-failure',
    // page.route() does not see requests a service worker sends; the PWA spec allows it.
    serviceWorkers: 'block',
  },
  projects: [
    { name: 'phone', use: { ...devices['Pixel 7'] } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  ],
});
