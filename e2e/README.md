Playwright E2E tests for TFGv3

Requirements:
- Node.js (>=16)
- The backend server running at `http://localhost:8000` (uvicorn)
- The frontend dev server running at `http://localhost:5173` (or allow Playwright to start it)

Quick start (PowerShell):

```powershell
cd e2e
npm install
npx playwright install --with-deps
# Start backend (in another terminal):
# cd ../ && poetry run uvicorn backend.app:app --reload --port 8000
# Start frontend (in another terminal):
# cd frontend && npm run dev
# Run tests
npm test
```

Notes:
- Tests inject an auth token in `localStorage` before loading the frontend, so they don't rely on the UI login flow (but they do exercise the UI project creation prompt and chat interactions).
- If `register` fails because the email already exists, the test attempts to login as fallback.
- Adjust `API_BASE` and `FRONTEND` inside `e2e/tests/e2e.spec.ts` if your servers use different ports.
