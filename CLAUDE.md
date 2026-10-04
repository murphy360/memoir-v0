# Working on memoir

Instructions for any Claude session in this repository. Built from murphy360/standards (templates/CLAUDE.md); keep
the shared parts as they are and add what is particular to this project under "This project".

## How work arrives

The owner hands out work as a ticket (or "the next ticket in the milestone"). The milestone's description carries the
RUN ORDER: take the first open ticket in it that is not assigned to the owner and is not an epic. Read the whole
ticket, including its "For the implementer" section. If a decision the owner reserved is unclear, ask in one comment
on the ticket and take the next one; never guess. Say on the ticket, in one comment, that you started and which branch.

## Where and how to work

- Never change the branch of the main checkout: the owner may be using it. Work in a scratch worktree:
  `git worktree add -b <type>/<short-name> /tmp/<project>-wt/<short-name> origin/main`
  (types: feat/, fix/, docs/, ci/, deploy/). Remove the worktree when the PR is open.
- Tests run in the project's Docker image, not on the host. Build it under your own tag so parallel sessions never
  overwrite each other's images.
- Never touch the owner's running services, stacks or devices unless the ticket says so.

## Definition of done: one pull request

1. The change, small and readable, in the files the ticket names.
2. A unit test for every new behaviour, green in Docker; the PR body pastes the last lines of the output.
3. The documentation in the same PR: the spec for the area, the user-facing manual, and a training or how-to line
   where the project has them. Write for the reader, not the developer.
4. The commit: the first line says what changed in plain words; the body says why; `Closes #N`; a `Note:` line for
   anything the deployer must do.
5. The PR body: what and why, `Closes #N`, the tests and their output, the docs touched, any known issue with its
   ticket. Open it with `gh pr create --base main`, then comment the link on the ticket.
6. Never merge, never push to main, never enable auto-merge, unless the owner has said so for this session.

## Standards every project keeps (murphy360/standards)

- CI calls the shared workflows at a pinned version tag: standards-check, python-lint (ruff at its defaults, 88
  columns, `ruff format`) or node-lint (ESLint, Prettier's defaults), shell-lint, actionlint, test-docker, image.
- The code rules ratchet (`code_rules_baseline.json`): complexity 15, 15 branches and 60 statements per function,
  800 lines per file (1200 for a test). Never add to a file over the limit; split it in a PR of its own first. When
  you fix a finding, lower the baseline in the same PR (`code_rules.py --update`).
- Every third-party action is pinned to a commit SHA; Dependabot (`.github/dependabot.yml`) keeps them and the
  dependencies current, one grouped PR per ecosystem per week.
- Times are UTC. Secrets never go in the repository, a ticket or a log.
- Prose in docs and tickets: short sentences, one idea per sentence, no em-dashes.

## This project

A voice-first personal memory timeline for one household: record or upload a memory, the API transcribes and
analyses it with Gemini, files photos and faces (CompreFace), and the web app shows a timeline of periods, epics
and events. Two images from one repository:

- `backend/`: FastAPI on Python 3.12, SQLite at `/data/memoir.db`, audio and documents under `/data`. Image
  `ghcr.io/murphy360/memoir-v0-api`. Settings are environment variables (see `docker-compose.yml`); no key means that
  feature is off (no `GEMINI_API_KEY`: no transcription; no `COMPREFACE_API_KEY`: no faces).
- `frontend/`: Next.js 14 (app router, client components) on Node 22. Image `ghcr.io/murphy360/memoir-v0-web`. The
  browser talks to the API at `API_BASE` (`frontend/app/lib/memoirApi.ts`): an absolute URL for local development,
  otherwise the same origin under the base path. `NEXT_PUBLIC_BASE_PATH` and `NEXT_PUBLIC_API_BASE_URL` are inlined
  at build time, so they are Docker build arguments; the image defaults are the hosted deployment (`/memoir-v0`).
- Tests and lint: `make test`, `make lint`, `make format` (all in Docker, `TAG=<you>` for your own image tags).
  The API tests use a throwaway SQLite database (`backend/tests/conftest.py`) and never call Gemini or CompreFace.
  The ratchet baselines live in `backend/` and `frontend/`; `make baseline` rewrites them with a checkout of
  murphy360/standards beside this repository. `backend/app/main.py` and `frontend/app/page.tsx` are far over the
  file-size limit: add nothing to them, put new routes in a router module and new UI in a component.
- Local run: `docker compose up --build` (web on :3000, API on :8001, a CompreFace stack of its own on :8080).
- Hosted on the owner's server from the dontpanic stack (`~/Software/dontpanic`, services `memoir-v0-api` and
  `memoir-v0-web`) behind Caddy at `https://dontpanic.ddns.net/memoir-v0`, with Caddy's basic auth in front, beside
  the rewrite (murphy360/memoir) at `/memoir`. Caddy strips `/memoir-v0` from `/memoir-v0/api/*` for the API and
  passes the rest to the web app. Data in `/docker/memoir/data`, secrets in `/docker/memoir/v0.env`; the
  CompreFace there is the stack's shared one. Never in the repository.
- Memories, photos and faces are private family data. Never log transcripts or send them anywhere but the
  configured Gemini and CompreFace endpoints; keep the basic auth in front of every route.
