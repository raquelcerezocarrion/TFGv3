Playwright E2E tests for TFGv3

Requirements:
- Node.js (>=16)
- The backend server running at `http://localhost:8000` (uvicorn)
- The frontend dev server running at `http://localhost:5173`

Quick start (PowerShell):

```powershell
cd e2e
npm install
npm run install-playwright
# Start backend (in another terminal):
# cd ../ && poetry run uvicorn backend.app:app --reload --port 8000
# Start frontend (in another terminal):
# cd frontend && npm run dev
# Run tests
npm run test:e2e
```

Notes:
- Tests are intentionally minimal and non-invasive: they only check the backend `/health` endpoint and that the frontend serves the login UI. This avoids creating users, projects, or other state that could collide with existing TDD tests.
- Adjust `API_BASE` inside `e2e/tests/e2e.spec.ts` if your backend uses a different port.
