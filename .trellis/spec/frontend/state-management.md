# State Management

> How state is managed in this project.

---

## Overview

The frontend has not selected a global state library yet. Until that happens,
keep state choices simple and explicit. This UI has four distinct state classes:

- local interaction state
- server state
- URL state
- optional cross-view workflow state

Do not introduce a store just because props feel inconvenient.

---

## State Categories

- Local state: selected row, selected table, current PDF page, zoom level,
  filter chips, modal visibility.
- Server state: task status, extraction results, confidence scores, review
  flags, BBox payloads, retrigger outcomes.
- URL state: task ID, selected table code, and other values worth deep-linking.
- Cross-view workflow state: only state that truly needs to survive route
  changes and be consumed in multiple distant parts of the app.

---

## When to Use Global State

- Start with local state inside the owning feature view or composable.
- Promote state to a global store only when it must survive route changes or is
  consumed by more than two distant branches of the UI.
- Do not add Pinia or another store by default until the project explicitly
  decides it is needed.
- Keep server state out of an ad hoc global store if a request-scoped or
  feature-scoped model is enough.

---

## Server State

- Key server state by stable backend identifiers such as `task_id` and
  `target_table_code`.
- Preserve backend status distinctions exactly. `SUCCESS`, `NOT_DISCLOSED`, and
  `NOT_FIND` are different render states and review states.
- Keep review-required state tied to confidence and backend status, not to
  inferred frontend heuristics.
- Avoid copying the same extraction payload into multiple stores or feature
  trees.

---

## Common Mistakes

- Mixing UI-only selection state into persisted server-state models.
- Flattening review-needed and completed data into a simple boolean that loses
  backend meaning.
- Treating page number, BBox, and selected row as unrelated state when they must
  remain synchronized for traceability.
- Introducing a global store before the application has enough real code to
  justify it.

---

## Examples

- `requirement.md`: section 3.7 defines synchronized left-pane and right-pane
  review state.
- `design.md`: Phase 5 and Phase 6 define the server-state fields the UI must
  preserve.
- `design.md`: section 4.2.1 defines partial retrigger flows that should update
  only the affected task/result state.
