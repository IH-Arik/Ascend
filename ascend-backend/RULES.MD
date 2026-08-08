# Rules

## Repository Rules

- keep code module-based
- keep route handlers thin
- prefer explicit naming over clever abstractions
- do not mix unrelated domain logic into shared utilities
- document important design changes

## Documentation Rules

- update docs when scope changes
- record major technical choices in `docs/DECISIONS.md`
- record notable repository changes in `docs/CHANGELOG.md`
- when Figma screenshots arrive, compare them against the DOCX first and update the matching Markdown docs before coding
- use `docs/FIGMA_DOCX_WORKFLOW.md` as the operating rule for screen-by-screen backend planning

## Security Rules

- never hardcode secrets
- never trust frontend role claims
- protect sensitive fields by default
- audit high-sensitivity operations

## Product Rules

- first-use onboarding flow is a core requirement
- current OPS should not be treated as valid until first-use flow completes
- leadership visibility should remain appropriately restricted
- medical-record-related behavior must follow minimum-necessary access

## Collaboration Rules

- keep tasks updated
- leave concise status notes in `UPDATE.MD`
- avoid large untracked architectural changes
