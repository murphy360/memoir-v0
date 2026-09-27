# memoir
Memoir is a voice-first personal memory platform that helps people capture life stories, organize them into a timeline, and receive guided follow-up prompts that uncover deeper details over time.

## Project Goals

- Make memory capture effortless with quick voice recording from mobile devices.
- Convert spoken memories into accurate, searchable text.
- Build a living timeline based on when events happened, not only when they were recorded.
- Use AI to ask personalized follow-up questions that help users expand incomplete memories.
- Give users strong ownership and privacy controls for their personal data.

## Requirements

- Docker (required): this project is built and run in Docker containers.

## What We Are Building

Memoir follows a Client-Server-AI architecture:

- Frontend: A mobile-responsive web app for recording audio, reviewing transcripts, and viewing timeline entries.
- Backend API: Handles uploads, orchestrates AI processing, stores results, and serves timeline data.
- AI Processing: Speech-to-text transcription, temporal extraction, emotion/context tagging, and follow-up question generation.
- Storage: Object storage for raw/processed audio and a relational database with vector search for memory retrieval.

## Memory Processing Pipeline

### 1. Transcription

- Input: User audio recording.
- Process: Normalize/compress audio, then transcribe with a high-accuracy STT model.
- Output: Transcript text and basic confidence metadata.

### 2. Chronological Extraction

- Input: Transcript text.
- Process: LLM extracts temporal markers and event details.
- Output: Structured JSON with:
	- event_description
	- estimated_date
	- emotional_tone

### 3. Timeline Insertion

- Input: Structured event data and transcript.
- Process: Save timeline entries and embeddings for semantic retrieval.
- Output: Chronological + semantic memory index.

### 4. Interactive Memory Loop

- Input: Newly processed memory entry.
- Process: Detect missing context, generate one personalized follow-up prompt.
- Output: AI nudge shown in dashboard or notification channel.

## MVP Scope

- Record and upload audio from the web app.
- Generate and display transcript text.
- Extract a best-effort event date from transcript text.
- Show timeline entries sorted by extracted event date.
- Generate a single follow-up question after each new memory.
- Let a user trigger a research pass that adds fact-checking context and likely historical leads for a memory.

## Privacy and Data Ownership

- Encrypt audio files and transcripts at rest.
- Minimize or scrub sensitive PII before third-party AI processing.
- Keep per-user data isolated and access-controlled.
- Provide user data export in JSON (and later PDF) formats.

## Suggested Stack (Initial)

- Frontend: Next.js + Tailwind CSS
- Backend: FastAPI or Node.js API
- Audio preprocessing: FFmpeg
- Database: PostgreSQL + pgvector
- Object storage: AWS S3
- Auth: Clerk or Auth0
- Orchestration: LangChain (optional in early MVP)

## Development Phases

1. Recording + transcription vertical slice.
2. Timeline extraction and storage.
3. Interactive follow-up question generation.
4. Retrieval quality improvements and production hardening.

## Current MVP Implementation (April 2026)

The repository now includes a working Dockerized MVP with two services:

- `web`: Next.js app with MediaRecorder-based audio capture and timeline UI.
- `api`: FastAPI app that accepts audio uploads and runs a basic memory-processing flow.

Current backend behavior:

- Accepts audio uploads at `POST /api/memories`.
- Converts uploaded recordings to MP3 and persists them under backend storage (`/data/audio` in Docker).
- Runs transcription and analysis during memory processing via Gemini.
- Uses Gemini function-calling to set structured memory metadata (best-effort date precision, recorder name, referenced people, and referenced locations).
- Lets the user trigger Gemini-backed research notes for a saved memory to surface likely context and open questions to verify.
- Stores memories in SQLite and returns timeline entries from `GET /api/memories`.
- Returns a playable audio endpoint per memory at `GET /api/memories/{id}/audio`.

## Run With Docker

Docker is the only requirement; nothing runs on the host.

1. Copy `.env.example` to `.env`. Set `GEMINI_API_KEY` for transcription and analysis, and `COMPREFACE_API_KEY`
   once you have created a Recognition service in the local CompreFace UI. Either may stay empty: that feature is
   off until it is set.
2. Build and start the services:

```bash
docker compose up --build
```

3. Open the app:

- Frontend: `http://localhost:3000`
- API health: `http://localhost:8001/api/health`
- CompreFace UI: `http://localhost:8080`

4. Stop the services with `docker compose down`. Data stays in the `memoir_data` volume.

## Development

This project follows [murphy360/standards](https://github.com/murphy360/standards): the shared CI workflows, ruff
and Prettier at their defaults, the code-rules ratchet, Dependabot, and `CLAUDE.md` for agent sessions.

| Command | What it does |
|---|---|
| `make test` | Builds the `test` image targets and runs pytest (backend) and the typecheck plus tests (frontend) |
| `make lint` | ruff and ESLint, with the formatting checks |
| `make format` | `ruff format` and `prettier --write` |
| `make baseline` | Rewrites the ratchet baselines after a clean-up (needs `../standards`) |

CI (`.github/workflows/ci.yml`) runs the same checks and publishes two images on `main`:
`ghcr.io/murphy360/memoir-api` and `ghcr.io/murphy360/memoir-web`. The complexity and file-size limits are enforced
against `code_rules_baseline.json` in `backend/` and `frontend/`: what is there today may only go down. The largest
files (`backend/app/main.py`, `frontend/app/page.tsx`) are over the limit, so new code goes in new modules.

## Hosting

The images are built for one deployment: the web app served under `/memoir` and the API on the same origin, so
that a reverse proxy can put both behind one hostname and one login. The frontend's `NEXT_PUBLIC_BASE_PATH`
(default `/memoir`) and `NEXT_PUBLIC_API_BASE_URL` (default empty, meaning same origin) are build arguments.

The owner's deployment lives in the dontpanic stack at `https://dontpanic.ddns.net/memoir`:

- Caddy asks for basic auth on everything under `/memoir`, strips `/memoir` from `/memoir/api/*` and proxies it to
  `memoir-api:8000`, and proxies the rest to `memoir-web:3000`.
- `memoir-api` keeps its data in `/docker/memoir/data` and reads its secrets (`GEMINI_API_KEY`,
  `COMPREFACE_API_KEY`) from `/docker/memoir/memoir.env`. It uses the stack's shared CompreFace at
  `http://compreface-api:8080`; the key is a Recognition service created for Memoir in that CompreFace UI.
- Deploy a new build with `docker compose pull memoir-api memoir-web && docker compose up -d memoir-api memoir-web`.

## API Endpoints (MVP)

- `GET /api/health`: Health status.
- `GET /api/memories`: Returns processed memories in timeline order.
- `POST /api/memories`: Accepts multipart form-data with `audio` file and returns processed memory metadata including date labels and relationship/location tags when available.
- `POST /api/memories/{id}/research`: Generates or refreshes a stored research note for a memory using its transcript and extracted metadata.
- `POST /api/memories/{id}/reanalyze`: Re-runs transcription and metadata extraction on stored audio for an existing memory.
- `DELETE /api/memories/{id}`: Deletes a memory entry and its stored audio file.
- `GET /api/memories/{id}/audio`: Streams the stored MP3 recording for playback.
