# AGENTS

## Purpose

Define how human contributors and coding agents should work inside this repository.

## Core Expectations

- respect the module-based structure
- keep business logic out of route handlers
- update docs when architecture or scope changes
- avoid introducing hidden coupling across modules
- keep role and permission logic explicit

## Working Rules

- read `docs/ARCHITECTURE.md` and `docs/MODULE_MAP.md` before major changes
- check `docs/DECISIONS.md` before making architectural assumptions
- update `docs/CHANGELOG.md` for meaningful scaffold or behavior changes
- update `TASKS.MD` when starting or finishing meaningful work
- update `UPDATE.MD` with short status notes after major milestones

## Implementation Priorities

1. correctness
2. traceability
3. clarity
4. extensibility

## Module Change Rule

When creating a new module feature:

- add or update module docs if scope changed
- keep schemas and services near the module
- avoid putting module-specific constants into shared folders unless reused broadly

## Sensitive Domains

Extra care is required for:

- auth
- permissions
- OPS scoring
- medical records
- exports
- audit logging
