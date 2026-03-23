# Frontend Development Guidelines

> Best practices for frontend development in this project.

---

## Overview

The repository does not yet contain committed frontend implementation code.
These frontend guidelines are therefore bootstrapped from the current product and
architecture documents:

- `requirement.md`
- `design.md`

The selected frontend direction is a Vue 3 application built for traceable,
review-friendly financial extraction workflows. Until code exists, treat these
documents as the intended implementation baseline and keep them updated when the
first UI decisions are committed.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Feature layout for the Vue frontend | Bootstrapped from design |
| [Component Guidelines](./component-guidelines.md) | Vue SFC and interaction patterns | Bootstrapped from design |
| [Hook Guidelines](./hook-guidelines.md) | Vue composable patterns for async UI logic | Bootstrapped from design |
| [State Management](./state-management.md) | Local state, server state, review workflow state | Bootstrapped from design |
| [Quality Guidelines](./quality-guidelines.md) | UI review bar for finance and traceability features | Bootstrapped from design |
| [Type Safety](./type-safety.md) | Frontend contract typing and bigint-safe handling | Bootstrapped from design |

---

## Pre-Development Checklist

1. Read this index first.
2. Read `directory-structure.md` before creating any new view or feature.
3. Read `component-guidelines.md` and `hook-guidelines.md` before implementing
   PDF interaction, polling, or review UI.
4. Read `state-management.md` and `type-safety.md` before shaping API results in
   the UI.
5. Read `quality-guidelines.md` before review or merge.
6. Read `../guides/cross-layer-thinking-guide.md` when the change affects task
   status, result payloads, BBox shape, or review semantics.

---

## Scope Reminder

The design already fixes several frontend realities:

- The UI is Vue 3, not React.
- The main review surface is a dual-pane layout: structured result on the left,
  PDF preview on the right.
- BBox-backed provenance is a first-class feature, not an optional debug panel.

Do not introduce React- or Next-specific conventions into this frontend unless
the architecture is intentionally changed.
