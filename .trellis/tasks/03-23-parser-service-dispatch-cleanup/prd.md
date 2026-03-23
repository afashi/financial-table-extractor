# Parser Service Skeleton And Dispatch Cleanup

## Goal
Finish the current uncommitted backend work so the new core-service dispatch flow
and parser-service skeleton are coherent, verified, and ready for human testing
and commit.

## Requirements
- Keep the scope limited to the current parser/core uncommitted changes.
- Ensure `POST /api/v1/extract` dispatch behavior remains correct with MinIO and
  Redis integration.
- Ensure parser queue consumption updates task status through
  `QUEUED -> PARSING -> PARSED/FAILED`.
- Ensure the parser skeleton writes a minimal valid `content_list.json`
  artifact to MinIO.
- Ensure failure paths persist stable task status and remarks for retry and
  diagnosis.
- Ensure local runtime commands and entrypoints are usable for manual testing.
- Keep the documented contracts in sync with the implemented behavior.

## Acceptance Criteria
- [ ] Core-service dispatch flow passes automated tests.
- [ ] Parser-service worker flow passes automated tests.
- [ ] `python -m apps.parser_service.app.main` is a valid runnable entrypoint.
- [ ] Real local smoke flow can create a task, consume the queue message, write
      `content_list.json`, and leave the task in `PARSED`.
- [ ] No known failing lint/test issues remain in the current diff.
- [ ] Updated docs describe the current implemented contract without claiming
      more than exists.

## Technical Notes
- This is a backend and cross-layer cleanup task.
- Focus areas are queue payloads, object storage contracts, task status
  lifecycle, runtime startup behavior, and current tests.
- Avoid broad schema expansion unless a concrete bug requires it.
