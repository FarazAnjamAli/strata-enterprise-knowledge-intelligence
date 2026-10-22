# Contributing

1. Fork, then create a branch: `git checkout -b feat/short-name`.
2. Backend: `cd backend && pip install -r requirements-dev.txt`, then `ruff check . && ruff format . && pytest`.
3. Frontend: `cd frontend && npm ci`, then `npm run lint && npm run typecheck && npm run build`.
4. Keep commits focused, and describe what changed and how you tested it in the PR.

Conventions: Python is formatted with ruff (line length 110). TypeScript is strict, and Tailwind uses the design tokens in `tailwind.config.ts`. UI copy is short, plain and free of em dashes.
