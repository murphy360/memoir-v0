---
description: "Use when making code changes, fixing bugs, refactoring, or preparing a PR. Enforce repository lint rules and do not mark work complete until lint is green."
name: "Linting Gate"
applyTo: "**"
---
# Linting Gate

- Treat lint and tests as a hard completion gate for every coding task.
- Run `make lint` and `make test` from the repository root. Both run in the project's Docker images (see CLAUDE.md).
- `make format` applies ruff format (backend) and Prettier (frontend). Formatting is checked in CI.
- The complexity and file-size limits come from murphy360/standards with a ratchet (`code_rules_baseline.json` in
  `backend/` and `frontend/`). Never add to a file over the limit. When you fix a finding, lower the baseline in the
  same PR (`make baseline`).
- If lint fails, fix the issues before reporting completion.
- If lint cannot run because of environment or tooling problems, report the blocker and exact failing command/output.
- Do not claim success while lint is failing or unverified.
