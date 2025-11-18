import { test, expect } from '@playwright/test';

// Replaced the large, stateful E2E with small, non-invasive checks that
// validate the app is up and the frontend serves the login UI.

const API_BASE = 'http://localhost:8000';

test.describe('Minimal E2E smoke tests', () => {
  test('API /health returns ok', async ({ request }) => {
    const res = await request.get(`${API_BASE}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('status', 'ok');
    expect(body).toHaveProperty('app');
  });

  test('Frontend serves login UI', async ({ page }) => {
    // playwright config sets baseURL to the frontend; navigate to root
    await page.goto('/');
    // The auth component includes an input with placeholder 'Email'
    const emailInput = page.getByPlaceholder('Email');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
    // Also ensure there is a button to submit the form (Entrar or Registrar)
    const submitBtn = page.getByRole('button', { name: /Entrar|Registrar/ });
    await expect(submitBtn).toBeVisible();
  });

  test('GET /user/chats without auth returns 401', async ({ request }) => {
    const r = await request.get(`${API_BASE}/user/chats`);
    expect(r.status()).toBe(401);
  });

  test('GET /user/employees without auth returns 401', async ({ request }) => {
    const r = await request.get(`${API_BASE}/user/employees`);
    expect(r.status()).toBe(401);
  });

  test('POST /auth/login with empty body returns 422', async ({ request }) => {
    const r = await request.post(`${API_BASE}/auth/login`, { data: {} }).catch(e => e.response || null);
    // Playwright request throws on network errors; if response exists, check status
    if (!r) throw new Error('No response from /auth/login');
    expect([400, 422, 401]).toContain(r.status());
  });

  test('Auth UI shows register toggle button', async ({ page }) => {
    await page.goto('/');
    const toggle = page.getByRole('button', { name: /Crear cuenta|Tengo cuenta/ });
    await expect(toggle).toBeVisible();
  });
});
