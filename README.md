# Dental Patient Management: Backend

**Live API:** https://dental-client-management-backend.onrender.com/docs

## 1. Project overview

A REST service for a dental clinic.

- **Patients:** add, edit, search, sort, paginate. IDs come from an atomic counter.
- **Case sheets:** Chief Complaint, Investigation, Diagnosis, embedded in the patient document. Drafts allowed; the server sets the status.
- **Dashboard:** counts plus a registration trend (last 6 months, a year, or a month), using parallel aggregations.
- **AI summary:** regenerated in the background after each change. A SHA-256 fingerprint marks it outdated.
- **AI chatbot:** stateless, grounded in the patient's record (never invents facts). Gives labelled suggestions when asked.

**Structure:** `routes → services → repositories`

```
app/
├── api/v1/         # routes
├── services/       # business logic, AI client
├── repositories/   # MongoDB queries
├── schemas/        # request/response validation
├── core/           # config, database, errors, rate limiting
└── prompts/        # AI instructions
```
## 2. Technologies used

Python · FastAPI · MongoDB Atlas · Google Gemini API · Docker · Render

## 3. Backend setup

Requires Docker and/or [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/heykvr/dental-client-management-backend.git
cd dental-client-management-backend
cp .env.example .env      # replace the <placeholders> (see section 5)
```

Tests (use a local MongoDB and a fake AI, so no key needed):

```bash
uv sync
docker compose up -d mongo
uv run pytest
```

## 4. MongoDB setup

- **Local:** `docker compose up -d mongo`
- **Atlas:** create a free cluster, allow your IP under Network Access, and put the URI in `MONGODB_URI`.

The app creates its indexes and ID counter on startup; there's nothing to set up by hand.

| Collection | Holds |
|---|---|
| `patients` | Patient details and the embedded `case_sheet` (sections, `status`, `ai_summary`) |
| `counters` | `{_id: "patient_id", seq}`, used for IDs like `PAT-0001` |

## 5. Environment variables required

| Variable | Example |
|---|---|
| `MONGODB_URI` | `mongodb://localhost:27017` or your Atlas URI |
| `MONGODB_DB_NAME` | Any name, e.g. `dental_app` |
| `GEMINI_API_KEY` | Your key (secret) |
| `AI_MODEL` | Any Gemini model (default `gemini-3.5-flash-lite`) |
| `AI_CHAT_TIMEOUT_SECONDS` | `15` |
| `AI_SUMMARY_TIMEOUT_SECONDS` | `20` |
| `CORS_ORIGINS` | `http://localhost:5173` |
| `RATE_LIMIT_DEFAULT` | `10/minute` |
| `RATE_LIMIT_AI` | `3/minute;20/day` |
| `APP_TIMEZONE` | `Asia/Kolkata` |
| `ENVIRONMENT` | `development` (DEBUG logs) or `production` (INFO logs) |

`.env` is git-ignored. In production these are set in Render's environment settings.

## 6. AI API setup

1. Get a free key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Set `GEMINI_API_KEY` in `.env`.

The key stays on the server; the browser never calls Gemini directly.

## 7. Steps to run the application locally

**Option A: Docker** (API + local MongoDB)

```bash
docker compose up --build
```

The API runs at http://localhost:8001 (docs at `/docs`).

**Option B: without Docker** (set `MONGODB_URI` to your Atlas URI)

```bash
uv sync
uv run uvicorn app.main:app --reload
```

The API runs at http://localhost:8000 (docs at `/docs`).

For the UI, follow the [frontend README](https://github.com/heykvr/dental-client-management-frontend#readme).

## 8. Assumptions and known limitations

**Assumptions**
- Only clinic staff add patients; there is no public sign-up.
- One clinic, in one timezone: IST.
- Date of birth is stored and age is calculated from it.
- A case sheet is complete when complaint, tooth/area, findings, tenderness and diagnosis are all filled. Duration and sensitivity are optional.
- Chat history lives in the browser (30 minutes); nothing is stored on the server.

**Known limitations**
- No authentication yet (next step: JWT).
- Rate limits are in memory (next step: Redis).
- Render's free tier sleeps, so the first request takes 30–60 s.
- Atlas allows all IPs (`0.0.0.0/0`) because Render's free tier has no static IP. Access is protected by credentials and TLS.
- Gemini's free tier has tight limits and may use prompts for training, so use demo data only.

## 9. Next steps

- **CI:** GitHub Actions runs Ruff and pytest (with a MongoDB service container) on every pull request, and a failing check blocks the merge.
- **CD:** Render deploys only after CI passes on `main`. After each deploy, a smoke test calls `/health` and a few key routes.
- **Environments:** separate staging and production, each with its own Atlas database, Gemini key and env vars. Changes go to staging first.
- **Security:** JWT login with roles, Redis-backed rate limits, and a static outbound IP allow-listed in Atlas.
