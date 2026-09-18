# CampusOS — Local Development Without Docker

This guide runs every CampusOS component directly on your machine:

```text
PostgreSQL :5432
Redis      :6379
FastAPI    :8000
Celery     background worker
Frontend   :5173
```

Docker is not required.

## Prerequisites

Install:

- Python 3.12
- PostgreSQL 16
- Redis 7 or a Redis-compatible local server
- Git

Verify:

```bash
python --version
psql --version
redis-cli ping
```

`redis-cli ping` should return `PONG`.

## 1. Clone and create the Python environment

```bash
git clone https://github.com/MridulJain0771/CampusOS.git
cd CampusOS
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### macOS / Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

## 2. Create the PostgreSQL database

Open PostgreSQL as an admin user:

```bash
psql -U postgres
```

Then run:

```sql
CREATE USER campus WITH PASSWORD 'campus';
CREATE DATABASE campus OWNER campus;
\q
```

If the user/database already exists, keep the existing objects and make sure the credentials match `.env`.

Default connection:

```text
postgresql+asyncpg://campus:campus@localhost:5432/campus
```

## 3. Start Redis

Linux:

```bash
sudo systemctl start redis-server
```

macOS with Homebrew:

```bash
brew services start redis
```

Windows can run Redis through WSL or another Redis-compatible local installation. Confirm it is reachable:

```bash
redis-cli ping
```

## 4. Create local environment configuration

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

The default development values are already aligned with the local PostgreSQL and Redis ports.

Important variables:

```dotenv
DATABASE_URL=postgresql+asyncpg://campus:campus@localhost:5432/campus
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
BOOTSTRAP_SUPERADMIN_EMAIL=admin@campusos.io
BOOTSTRAP_SUPERADMIN_PASSWORD=change-this-admin-password
```

Keep the bootstrap credentials stable once the super-admin has been created in a database. Changing the environment variable does not rewrite an existing password hash.

## 5. Apply database migrations

```bash
alembic upgrade head
```

You can inspect migration state with:

```bash
alembic current
alembic history
```

## 6. Run the backend

Terminal 1:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Liveness: http://localhost:8000/health/live
- Readiness: http://localhost:8000/health/ready
- Backend-served UI: http://localhost:8000/admin-ui/

On startup FastAPI creates the configured bootstrap super-admin if it does not already exist.

## 7. Run the Celery worker

Terminal 2:

macOS / Linux:

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO
```

Windows local development:

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

Redis databases are separated by purpose:

```text
/0 application/readiness
/1 Celery broker
/2 Celery result backend
```

## 8. Run the frontend separately

CampusOS does not require Node.js for the current admin UI.

Terminal 3:

```bash
cd frontend
python -m http.server 5173
```

Open:

http://localhost:5173

When served separately, the UI automatically calls:

```text
http://localhost:8000/api/v1
```

When the same files are served by FastAPI under `/admin-ui/`, the UI uses the current backend origin.

You can override the API endpoint during frontend development:

```text
http://localhost:5173/?api=http://127.0.0.1:8000/api/v1
```

FastAPI already allows the local frontend origin `http://localhost:5173` through CORS.

## 9. Run quality checks and tests

Terminal 4, from the repository root:

```bash
ruff check .
python -m compileall -q app
pytest -q tests/unit
pytest -q tests/integration
```

Integration tests require PostgreSQL and Redis to be running and use the bootstrap credentials from your environment.

For a clean integration-test database you can create a separate database:

```sql
CREATE DATABASE campus_test OWNER campus;
```

Then temporarily point `DATABASE_URL` to `campus_test`, run:

```bash
alembic upgrade head
pytest -q tests/integration
```

## Recommended terminal layout

```text
Terminal 1  FastAPI   uvicorn app.main:app --reload --port 8000
Terminal 2  Celery    celery -A app.workers.celery_app.celery_app worker ...
Terminal 3  Frontend  python -m http.server 5173
Terminal 4  Tests     ruff / pytest / alembic commands
```

## Common problems

### PostgreSQL connection refused

Confirm PostgreSQL is running and listening on port 5432.

### Redis readiness fails

Run:

```bash
redis-cli ping
```

The response must be `PONG`.

### Super-admin login returns 401

The super-admin may have been created previously with a different password. Keep the original password or recreate the local development database.

### Frontend opens but API calls fail

Confirm:

- backend is running on port 8000;
- frontend is opened as `http://localhost:5173`;
- browser developer tools do not show a CORS or connection error.

### Integration tests modify local data

The integration suite creates schools, users, students and finance records. Prefer a dedicated `campus_test` database when you want a disposable test environment.
