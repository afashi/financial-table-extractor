# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

Frontend quality for this project is about trust, not decoration. The UI is the
human review surface for a finance-oriented extraction system, so code quality is
measured by how clearly it preserves provenance, confidence, and business
semantics.

These guidelines set the baseline for the first Vue implementation.

---

## Forbidden Patterns

- Introducing React- or Next-specific patterns into this Vue 3 frontend.
- Hiding `confidence_score`, `needs_review`, `NOT_DISCLOSED`, or `NOT_FIND`
  behind vague generic labels.
- Rendering data without keeping the corresponding page/BBox provenance
  available.
- Polling forever after a task reaches a terminal status.
- Letting presentation code reinterpret backend financial semantics on its own.
- Using array indexes as stable keys for result rows when domain identifiers
  exist.

---

## Required Patterns

- Keep task status, data status, confidence, and provenance visible in the UI.
- Keep left-pane selection and right-pane PDF highlight behavior synchronized.
- Handle loading, error, empty, `NOT_DISCLOSED`, and `NOT_FIND` states
  explicitly.
- Keep transport code, domain mapping, and presentation code separate.
- Make review-required states visually obvious and keyboard accessible.
- Preserve backend terminology in the UI and code when it carries business
  meaning.

---

## Testing Requirements

- No frontend toolchain is committed yet, so bootstrap work should at least pass
  static review of state handling, type handling, and render-state coverage.
- When the first UI code lands, add component tests for:
  - result selection and highlight synchronization
  - confidence and review-state rendering
  - explicit rendering of `NOT_DISCLOSED` and `NOT_FIND`
- Add composable tests for polling start/stop behavior and retrigger refresh
  behavior.
- Run manual QA on the dual-pane review workflow before merge.

---

## Code Review Checklist

- Does the UI preserve BBox-backed provenance?
- Are no-data states still distinct and user-visible?
- Is task polling lifecycle-safe?
- Are bigint identifiers handled without precision loss?
- Is the selected result always traceable to a page and rectangle?
- Are review actions accessible by keyboard and visible without color-only cues?

---

## Examples

- `requirement.md`: section 3.7 defines the review UX the UI must implement.
- `requirement.md`: section 3.6 defines confidence-driven review behavior.
- `design.md`: Phase 6 defines the traceability interaction that should anchor
  frontend quality reviews.
