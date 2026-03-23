# Directory Structure

> How frontend code is organized in this project.

---

## Overview

No frontend source tree exists yet, but the product design already defines a
clear application shape: upload and task tracking, extraction result review, and
PDF/BBox traceability. The layout below is the target structure for the initial
Vue 3 frontend implementation.

---

## Directory Layout

```text
apps/web/
├── src/
│   ├── app/
│   ├── views/
│   ├── features/
│   │   ├── extraction/
│   │   └── review/
│   ├── components/
│   │   ├── common/
│   │   ├── pdf/
│   │   └── result-table/
│   ├── composables/
│   ├── services/
│   │   └── api/
│   ├── types/
│   ├── utils/
│   └── styles/
└── tests/
```

---

## Module Organization

- Organize by feature first. Upload/task monitoring and review/traceability are
  the main user journeys and should own their own view models, components, and
  API calls.
- Keep low-level PDF rendering and BBox overlay logic in `components/pdf/`.
- Keep tabular result rendering and drill-down UI in `components/result-table/`.
- Keep transport code in `services/api/`. This layer should know HTTP and DTOs,
  not DOM state.
- Keep shared reactive logic in `composables/`. A composable should not own
  markup.
- Keep contract types in `types/`, and keep feature-only presentation mappers
  near the feature that owns them.

---

## Naming Conventions

- Use `PascalCase.vue` for Vue components.
- Use `useXxx.ts` for composables.
- Use `kebab-case` for feature and route directories.
- Use descriptive domain names such as `ExtractionReviewView.vue`,
  `PdfPreviewPane.vue`, or `useTaskPolling.ts`.
- Keep API modules aligned with backend capabilities, for example
  `extract.ts`, `review.ts`, and `traceability.ts`.

---

## Examples

- `requirement.md`: section 3.7 defines the two-pane traceability UI.
- `design.md`: Phase 6 defines the UI interaction between result selection and
  PDF highlight rendering.
- `design.md`: Phase 0 and Phase 4 imply separate upload/task flows and review
  flows, which should become separate frontend features.
