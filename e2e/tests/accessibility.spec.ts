import { test } from '@playwright/test';

test('Basic accessibility audit (axe)', async ({ page }) => {
  // Adjust URL to your running frontend during tests (CI should start the app)
  await page.goto(process.env.PW_BASE_URL ?? 'http://localhost:5173');

  // Inject axe-core directly into the page
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });

  // Run axe in the page context and collect results
  const results = await page.evaluate(async () => {
    // @ts-ignore
    return await (window as any).axe.run();
  });

  console.log('Axe results:', JSON.stringify(results, null, 2));

  // Fail the test if there are any violations
  if (results.violations && results.violations.length > 0) {
    console.error('Accessibility violations found:', results.violations.length);
    throw new Error('Accessibility violations found. See console for details.');
  }
});
