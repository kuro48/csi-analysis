# Repository Guidelines

## Project Structure & Modules
- `frontend/`: Next.js + TypeScript UI (App Router under `src/app`, shared UI in `src/components`, API hooks in `src/services`).
- `backend/`: FastAPI service (`app/main.py` entrypoint, `app/api` routers, `app/models` SQLAlchemy models, `app/schemas` Pydantic, `app/services` business logic). Alembic migrations in `alembic/`.
- `zkp/`: Circom circuits, proofs, and helper scripts for zero-knowledge workflows.
- `scripts/`: Utility shell scripts; `start.sh` runs the full stack.
- `nginx/`, `sample/`, `docker-compose.yml`: Ops config, sample data, and container orchestration.

## Build, Test, and Development Commands
- One-shot stack: `./start.sh` (builds images, brings up docker-compose, performs basic health checks).
- Backend local: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`.
- Frontend local: `cd frontend && npm install && npm run dev` (Turbopack).
- Production-ish: `docker-compose up --build -d` (uses `docker-compose.yml`).
- Migrations: `cd backend && alembic upgrade head`.
- Lint/type-check frontend: `npm run lint`, `npm run type-check`; backend formatting via `black` and `isort` (see `pyproject.toml`).

## Coding Style & Naming Conventions
- Backend: Black line length 120, isort profile=black; prefer type hints; snake_case for Python modules/functions, PascalCase for classes.
- Frontend: ESLint + Next.js defaults; TypeScript strictness preferred; components PascalCase, hooks `useX`, files under `src/app` use route-based folders.
- Keep env-specific values in `.env`/`.env.local`; never commit secrets.

## Testing Guidelines
- Backend: `pytest backend/tests` for unit/integration; add fixtures over hard-coded IDs; cover new API paths with status and payload assertions.
- Frontend: No formal tests yet; at minimum run `npm run lint` and `npm run type-check` before pushes. Add React Testing Library tests under `src/__tests__` when introducing logic-heavy components.

## Commit & Pull Request Guidelines
- Commits: Present-tense, concise, scoped. Prefer Conventional-style prefixes when clear (`feat:`, `fix:`, `chore:`, `docs:`). Keep related changes together.
- PRs: Describe goal, key changes, and how to validate (commands, URLs). Link issues/tickets; include screenshots or GIFs for UI changes. Note schema or migration impacts and rollout steps. Ensure checks (lint/type-check/tests) are green before requesting review.

## Security & Configuration Tips
- Copy and edit example env files (`backend/.env.example`, `frontend/.env.local.example`); set strong `JWT_SECRET_KEY` and database credentials.
- Rotate and avoid placeholder secrets in configs, contracts, and scripts. Confirm Redis/Postgres endpoints before running tasks that touch data.
