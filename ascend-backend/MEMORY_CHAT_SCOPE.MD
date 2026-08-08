# Memory Chat Scope

## Purpose

Document what conversational memory or assistant-visible context should and should not persist across implementation discussions.

## In Scope

- current architecture decisions
- confirmed module names
- agreed role model
- accepted implementation order
- finalized data-model direction
- explicit product constraints confirmed by the team

## Out Of Scope

- temporary brainstorming ideas that were not approved
- sensitive credentials
- raw secrets
- private personal information not needed for product design
- speculative policy assumptions

## Usage Rule

Only treat something as stable project memory if it is:

- written in docs
- accepted in a project discussion
- reflected in implementation tasks or decisions

## Source Of Truth Order

1. code
2. `docs/DECISIONS.md`
3. `docs/ARCHITECTURE.md`
4. `TASKS.MD`
5. transient chat discussion

## Reminder

If chat discussion conflicts with repository docs, update the docs or explicitly resolve the conflict before building further.
