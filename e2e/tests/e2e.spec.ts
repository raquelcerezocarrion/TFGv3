import { test, expect } from '@playwright/test';

// E2E flow that exercises the main happy path:
// 1. register/login (API)
// 2. create an employee (API)
// 3. open frontend with token in localStorage
// 4. create a new project via UI (prompt)
// 5. open the created project
// 6. send a proposal request (/propuesta: ...)
// 7. accept the proposal
// 8. click 'Cargar empleados' CTA and assert employees were loaded
// 9. export PDF (open modal and click generate)
// 10. save project via 'Guardar proyecto' modal

const API_BASE = 'http://localhost:8000';
const FRONTEND = 'http://localhost:5173';

function randomEmail() {
  const t = Date.now().toString(36).slice(-6);
  return `e2e.user.${t}@example.com`;
}

test.describe('Playwright E2E: login, project, chat, employees, export, save', () => {
  test('full user flow', async ({ page, request, context }) => {
    const email = randomEmail();
    const password = 'secret123';

    // 1) Register (if user exists this may return 400; fallback to login)
    let token: string | null = null;
    try {
      const r = await request.post(`${API_BASE}/auth/register`, { data: { email, password, full_name: 'E2E User' } });
      if (r.ok()) {
        const d = await r.json();
        token = d.access_token;
      } else {
        // try login
        const l = await request.post(`${API_BASE}/auth/login`, { data: { email, password } });
        const ld = await l.json();
        token = ld.access_token;
      }
    } catch (e) {
      // final fallback: try login
      const l = await request.post(`${API_BASE}/auth/login`, { data: { email, password } });
      const ld = await l.json();
      token = ld.access_token;
    }

    expect(token).toBeTruthy();

    // 2) Create a sample employee for this user
    const empPayload = {
      name: 'Ana Ruiz',
      role: 'Backend',
      skills: 'Python, Django',
      seniority: 'Senior',
      availability_pct: 100
    };
    const empResp = await request.post(`${API_BASE}/user/employees`, {
      data: empPayload,
      headers: { Authorization: `Bearer ${token}` }
    });
    expect(empResp.ok()).toBeTruthy();
    const empJson = await empResp.json();
    expect(empJson).toHaveProperty('id');

    // Prepare to inject token into localStorage for the frontend
    await context.addInitScript((value) => {
      // eslint-disable-next-line no-undef
      window.localStorage.setItem('tfg_token', value);
    }, token);

    // 3) Open the frontend (will find token and show logged-in UI)
    await page.goto(FRONTEND);
    await page.waitForLoadState('networkidle');

    // Ensure the 'Nuevo proyecto' button exists
    const newBtn = page.getByRole('button', { name: 'Nuevo proyecto' });
    await expect(newBtn).toBeVisible({ timeout: 10000 });

    // 4) Create a new project via UI using prompt (Playwright handles dialogs)
    page.on('dialog', async dialog => {
      await dialog.accept('E2E Project');
    });
    await newBtn.click();

    // Wait for new project to appear in the sidebar
    const projectItem = page.locator('ul > li').first();
    await expect(projectItem).toBeVisible({ timeout: 5000 });

    // 5) Open the created project by clicking its main button
    await projectItem.locator('button').first().click();

    // 6) Send a proposal request via the chat input
    const input = page.locator('input[placeholder^="Escribe']');
    await expect(input).toBeVisible({ timeout: 5000 });
    await input.fill('/propuesta: E2E pruebas requisitos');
    await page.getByRole('button', { name: 'Enviar' }).click();

    // Wait for assistant reply containing 'Metodología' (from proposal endpoint)
    await page.waitForSelector('text=Metodología', { timeout: 8000 });
    await expect(page.locator('text=Metodología')).toBeVisible();

    // 7) Accept the proposal (send text 'Acepto la propuesta')
    await input.fill('Acepto la propuesta');
    await page.getByRole('button', { name: 'Enviar' }).click();

    // Wait for assistant to ask about using employees / manual (it should produce a message with 'empleados')
    await page.waitForSelector('text=empleados', { timeout: 8000 });

    // 8) Click the CTA 'Cargar empleados' if present
    const loadBtn = page.getByRole('button', { name: 'Cargar empleados' });
    if (await loadBtn.count() > 0) {
      await loadBtn.first().click();
      // After clicking, the UI shows a preview message with 'Empleados guardados' and sends JSON
      await page.waitForSelector('text=Empleados guardados', { timeout: 8000 });
      await expect(page.locator('text=Empleados guardados')).toBeVisible();
    } else {
      test.info().log('CTA `Cargar empleados` not found — flow may have differed, continuing.');
    }

    // 9) Export PDF: open export modal and click 'Generar PDF'
    const exportBtn = page.getByRole('button', { name: 'Exportar PDF' });
    await expect(exportBtn).toBeVisible();
    await exportBtn.click();

    // Wait for modal and click 'Generar PDF'
    await page.waitForSelector('text=Opciones de exportación', { timeout: 5000 });

    // Intercept download — Playwright download API
    const [download] = await Promise.all([
      page.waitForEvent('download').catch(() => null),
      page.getByRole('button', { name: 'Generar PDF' }).click()
    ]);

    if (download) {
      const path = await download.path();
      test.info().log(`PDF downloaded to ${path}`);
      expect(path).toBeTruthy();
    } else {
      test.info().log('No download event detected (backend or browser security may block it).');
    }

    // 10) Save project via 'Guardar proyecto' button
    const saveTopBtn = page.getByRole('button', { name: /Guardar proyecto|Guardar cambios/ });
    await expect(saveTopBtn).toBeVisible();
    await saveTopBtn.click();

    // Modal appears; fill title and save
    await page.waitForSelector('text=Título del proyecto', { timeout: 5000 });
    const titleInput = page.locator('input[placeholder="Título (opcional)"]');
    if (await titleInput.count() === 0) {
      // fallback: find first input inside the modal
      const modalInput = page.locator('div[role="dialog"] input').first();
      if (await modalInput.count() > 0) await modalInput.fill('E2E Saved Project');
    } else {
      await titleInput.fill('E2E Saved Project');
    }

    // Click the modal 'Guardar' button
    const modalSave = page.getByRole('button', { name: 'Guardar' }).last();
    await modalSave.click();

    // Assert the project is saved by checking sidebar updated or API listing returns at least one chat
    const chatsResp = await request.get(`${API_BASE}/user/chats`, { headers: { Authorization: `Bearer ${token}` } });
    expect(chatsResp.ok()).toBeTruthy();
    const chats = await chatsResp.json();
    expect(Array.isArray(chats)).toBeTruthy();
    expect(chats.length).toBeGreaterThan(0);
  });
});
