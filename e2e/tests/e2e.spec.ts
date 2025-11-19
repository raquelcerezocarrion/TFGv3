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

  test('POST /auth/register con email inválido devuelve 400 o 422', async ({ request }) => {
    const r = await request.post(`${API_BASE}/auth/register`, { data: { email: 'bad-email', password: 'secret123', full_name: 'X' } }).catch(e => e.response || null);
    if (!r) throw new Error('Sin respuesta de /auth/register');
    expect([400, 422]).toContain(r.status());
  });

  // --- Tests adicionales añadidos: New E2E ---
  test('POST /auth/register con contraseña corta devuelve 400/422', async ({ request }) => {
    const r = await request.post(`${API_BASE}/auth/register`, { data: { email: `itest+shortpw@example.com`, password: '12', full_name: 'Short PW' } }).catch(e => e.response || null);
    if (!r) throw new Error('Sin respuesta de /auth/register (short pw)');
    expect([400, 422]).toContain(r.status());
  });

  test('POST /projects/proposal funciona desde API (E2E)', async ({ request }) => {
    const payload = { session_id: `e2e-${Date.now()}`, requirements: 'Crear API de ejemplo para E2E' };
    const r = await request.post(`${API_BASE}/projects/proposal`, { data: payload }).catch(e => e.response || null);
    if (!r) throw new Error('Sin respuesta de /projects/proposal');
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty('methodology');
    expect(body).toHaveProperty('phases');
  });

  test('POST /export/chat.pdf devuelve PDF (E2E)', async ({ request }) => {
    const payload = { title: 'E2E Export', messages: [{ role: 'assistant', content: 'Metodología: breve. Equipo: 1 dev.' }] };
    const r = await request.post(`${API_BASE}/export/chat.pdf`, { data: payload }).catch(e => e.response || null);
    if (!r) throw new Error('Sin respuesta de /export/chat.pdf');
    expect(r.status()).toBe(200);
    const ct = r.headers()['content-type'] || '';
    expect(ct.includes('application/pdf')).toBeTruthy();
  });
});
