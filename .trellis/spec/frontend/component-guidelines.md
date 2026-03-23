# Component Guidelines

> How components are built in this project.

---

## Overview

This frontend is expected to be implemented with Vue 3. Components should make
financial review workflows easy to trust:

- provenance must stay visible
- no-data states must stay explicit
- selection in the left pane must map cleanly to the PDF highlight in the right
  pane

Because no UI code is committed yet, these are the baseline component rules for
the first implementation.

---

## Component Structure

- Use Vue single-file components with `script setup` and TypeScript.
- Separate feature containers from reusable presentation components.
- Let feature containers own data loading and orchestration.
- Let reusable components accept typed props and emit explicit events.
- Keep PDF viewer, overlay rendering, result table, and review controls as
  distinct components. Do not collapse the whole review screen into one file.

---

## Props Conventions

- Type every prop explicitly.
- Type every emitted event explicitly.
- Prefer narrow props over passing the full extraction payload everywhere.
- Pass stable identifiers, status fields, and BBox data as first-class props.
- Treat backend Snowflake-style IDs as strings in the UI to avoid bigint
  precision loss in JavaScript.
- If a component renders multiple result states, use discriminated props that
  preserve `SUCCESS`, `NOT_DISCLOSED`, and `NOT_FIND` as distinct cases.

---

## Styling Patterns

- TailwindCSS is the baseline styling direction documented in `design.md`.
- Use utility classes for layout, spacing, typography, and state colors.
- Keep canvas/PDF overlay math and any required absolute-position styles local
  to the PDF-related components.
- Avoid global style overrides for feature-specific visuals.
- Keep confidence and review states visually distinct and consistent across the
  UI.

---

## Accessibility

- Every interactive table row, review action, and page navigation control must
  be keyboard reachable.
- Selected result items need a visible focus/selected state in addition to PDF
  highlighting.
- Confidence and review state changes should have clear textual labels, not
  color only.
- The BBox highlight should always have a textual counterpart on the left side
  so the UI remains understandable even when PDF rendering fails.

---

## Common Mistakes

- Fetching remote data inside low-level presentational components.
- Passing raw backend payloads through many layers when a mapped view model would
  be clearer.
- Hiding low-confidence results or missing BBox data instead of showing the user
  that traceability is incomplete.
- Implementing the review screen as one giant component with upload, polling,
  table rendering, and PDF overlay logic all mixed together.

---

## Examples

- `requirement.md`: section 3.7 defines the user-facing traceability behavior.
- `design.md`: Phase 6 describes the interaction contract between selected data
  and PDF highlights.
- `requirement.md`: section 3.6 explains why confidence score and review state
  must remain visible in the UI.
