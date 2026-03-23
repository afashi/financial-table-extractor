# Hook Guidelines

> How hooks are used in this project.

---

## Overview

This file keeps the Trellis template name, but the project frontend is Vue 3.
That means the project should use Vue composables rather than React hooks.

Use composables for reusable reactive logic such as:

- task polling
- selection and BBox synchronization
- PDF viewport state
- review actions and retrigger flows

---

## Custom Hook Patterns

- Place shared reactive logic in `src/composables/useXxx.ts`.
- Keep network calls in `services/api/` and let composables coordinate loading
  state, retries, cancellation, and mapping to view-friendly state.
- Return a small, explicit surface from each composable: reactive state, derived
  state, and the actions the caller can trigger.
- Extract domain composables before copying watcher logic into multiple views.
- Likely early composables include `useTaskPolling`, `usePdfSelection`,
  `useBboxOverlay`, and `useReviewActions`.

---

## Data Fetching

- No query/caching library is committed yet. Do not assume Vue Query, Pinia
  plugins, or a global fetch wrapper exists.
- Keep HTTP functions in `services/api/` and wrap them with composables that own
  loading state and lifecycle cleanup.
- Poll task status by `task_id` until a terminal state is reached, then stop.
- Re-fetch review data after a retrigger or manual correction action that
  changes persisted results.
- If the project later adopts a query library, document query key conventions
  here before using it broadly.

---

## Naming Conventions

- Prefix composables with `use`.
- Name composables after user-visible capabilities, not generic technical
  details.
- Prefer names such as `useTaskPolling` or `usePdfSelection` over vague names
  like `useData` or `useState`.
- Keep UI-only helpers out of `composables/` if they are pure functions with no
  reactive behavior. Those belong in `utils/`.

---

## Common Mistakes

- Bringing React mental models directly into a Vue codebase.
- Running side effects at import time instead of inside composables.
- Creating multiple watchers that compete to update the same remote state.
- Leaving polling alive after the task has reached `FAILED`, `COMPLETED`, or
  `PENDING_REVIEW`.

---

## Examples

- `design.md`: Phase 0 and Phase 1 imply task creation plus status polling.
- `design.md`: Phase 6 implies a composable boundary between selected result
  rows and PDF/BBox highlight state.
- `design.md`: section 4.2.1 implies retrigger flows that should be isolated in
  their own composable logic.
