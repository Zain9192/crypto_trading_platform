# AI Crypto Trading Platform

Educational AI-based cryptocurrency trading, prediction, portfolio, and automated spot-trading platform based on the project SRS/SDD.

## Development workflow

Work is delivered feature-by-feature:

1. Branch from `main` using `feature/<name>`.
2. Implement only the feature scope.
3. Run local tests and CI.
4. Open a pull request into `main`.
5. Merge only after review and green checks.

## Foundation stack

- Frontend: React + TypeScript + Vite + Tailwind-ready structure
- Backend: FastAPI + Python
- Relational data: PostgreSQL
- Market/time-series data: MongoDB
- Cache: Redis
- Reverse proxy: Nginx
- Containers: Docker / Docker Compose
- CI: GitHub Actions

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health endpoint: `GET http://localhost:8000/api/v1/health`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

### Full stack with Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

## Current scope

This branch establishes the project foundation only. Trading, ML prediction, authentication, exchange connectivity, and portfolio business logic will be added on separate feature branches.
