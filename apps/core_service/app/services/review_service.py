from apps.core_service.app.schemas.review import ExtractedResultRead, ReviewQueueItem


class ReviewService:
    def __init__(self, *, session, task_repository, result_repository) -> None:
        self._session = session
        self._task_repository = task_repository
        self._result_repository = result_repository

    async def list_pending_review_tasks(self) -> list[ReviewQueueItem]:
        tasks = await self._task_repository.list_pending_review_tasks(self._session)
        queue: list[ReviewQueueItem] = []
        for task in tasks:
            pending_rows = await self._result_repository.list_pending_review_rows(
                self._session,
                task_id=task.id,
            )
            queue.append(
                ReviewQueueItem(
                    task_id=str(task.id),
                    doc_type=task.doc_type,
                    file_name=task.file_name,
                    update_time=task.update_time,
                    pending_result_count=len(pending_rows),
                    target_table_codes=[row.target_table_code for row in pending_rows],
                )
            )
        return queue

    async def get_task_results(self, *, task_id: int) -> list[ExtractedResultRead]:
        rows = await self._result_repository.list_by_task(self._session, task_id=task_id)
        return [
            ExtractedResultRead(
                result_id=str(row.id),
                target_table_code=row.target_table_code,
                data_status=row.data_status,
                extraction_route=row.extraction_route,
                confidence_score=str(row.confidence_score),
                needs_review=row.needs_review,
                table_data=row.table_data,
                fix_table_data=row.fix_table_data,
                remark=row.remark,
            )
            for row in rows
        ]
