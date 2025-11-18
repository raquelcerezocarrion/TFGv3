import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    headless: true,
    viewport: { width: 1280, height: 800 },
    actionTimeout: 30_000,
    navigationTimeout: 30_000,
    ignoreHTTPSErrors: true,
    baseURL: 'http://localhost:5173'
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } }
  ]
});
