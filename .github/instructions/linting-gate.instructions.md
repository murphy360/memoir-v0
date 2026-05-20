---
description: "Use when making code changes, fixing bugs, refactoring, or preparing a PR. Enforce repository lint rules and do not mark work complete until lint is green."
name: "Linting Gate"
applyTo: "**"
---
# Linting Gate

- Treat linting as a hard completion gate for every coding task.
- Run `make lint` from the repository root when available.
- If `make` is unavailable in the current shell, run `./lint.ps1` from the repository root instead.
- Keep file line length at or below 1000 characters.
- If lint fails, fix the issues before reporting completion.
- If lint cannot run because of environment or tooling problems, report the blocker and exact failing command/output.
- Do not claim success while lint is failing or unverified.
