import { test, expect } from '@playwright/test';
const API_BASE = 'http://localhost:8000';

test.describe('Minimal E2E smoke tests', () => {
  test('API /health returns ok', async ({ request }) => {
    const res = await request.get(`${API_BASE}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('status', 'ok');
    expect(body).toHaveProperty('app');
  });

  test('Frontend sirve la UI de login', async ({ page }) => {
    // la configuración de Playwright establece baseURL al frontend; navegar a la raíz
    await page.goto('/');
    // El componente de autenticación incluye un input con placeholder 'Email'
    const emailInput = page.getByPlaceholder('Email');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
    // También comprobar que existe un botón para enviar el formulario (Entrar o Registrar)
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

  test('POST /auth/login con cuerpo vacío devuelve error de validación', async ({ request }) => {
    const r = await request.post(`${API_BASE}/auth/login`, { data: {} }).catch(e => e.response || null);
    // Las peticiones de Playwright lanzan en errores de red; si hay respuesta, comprobar el status
    if (!r) throw new Error('Sin respuesta de /auth/login');
    expect([400, 422, 401]).toContain(r.status());
  });

  test('La UI de auth muestra el botón para alternar registro/login', async ({ page }) => {
    await page.goto('/');
    const toggle = page.getByRole('button', { name: /Crear cuenta|Tengo cuenta/ });
    await expect(toggle).toBeVisible();
  });
});
