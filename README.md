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

1. (Optional) Copy `.env.example` to `.env` and set `GEMINI_API_KEY` for preferred STT.
2. Build and start services:

```bash
docker compose up --build
```

3. Open the app:

- Frontend: `http://localhost:3000`
- API health: `http://localhost:8001/api/health`

4. Stop services:

```bash
docker compose down
```

## Linting

Use a single command to run backend and frontend lint checks:

- Windows (PowerShell):

```powershell
./lint.ps1
```

- Unix-like environments:

```bash
make lint
```

Initial baseline rules are intentionally lenient to catch low-hanging issues without blocking current development:

- Backend (Ruff):
	- Syntax/runtime checks (`E9`, `F63`, `F7`, `F82`)
- Backend (Pylint):
	- Advisory line length (`line-too-long`) at 140 chars
	- Advisory complexity (`too-complex`) max 25
	- Advisory file size guardrail (`too-many-lines`) max 2500 lines per module
- Frontend (ESLint):
	- Max file lines: 3000 (skip blank/comment lines)
	- Max function lines: 300 (skip blank/comment lines)
	- Max line length: 140 chars (ignoring URLs/strings/templates/comments)
	- Cyclomatic complexity: 25 (warning)

These thresholds are designed as a starting point and can be tightened incrementally after large legacy files are split. Backend advisory checks are currently non-blocking so teams can chip away at low-hanging cleanup first.

## API Endpoints (MVP)

- `GET /api/health`: Health status.
- `GET /api/memories`: Returns processed memories in timeline order.
- `POST /api/memories`: Accepts multipart form-data with `audio` file and returns processed memory metadata including date labels and relationship/location tags when available.
- `POST /api/memories/{id}/research`: Generates or refreshes a stored research note for a memory using its transcript and extracted metadata.
- `POST /api/memories/{id}/reanalyze`: Re-runs transcription and metadata extraction on stored audio for an existing memory.
- `DELETE /api/memories/{id}`: Deletes a memory entry and its stored audio file.
- `GET /api/memories/{id}/audio`: Streams the stored MP3 recording for playback.
