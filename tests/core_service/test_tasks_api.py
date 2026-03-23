import hashlib


async def test_create_and_fetch_task(async_client, test_app) -> None:
    file_bytes = b"%PDF-1.7\nfinancial-report"
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("report.pdf", file_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["deduplicated"] is False
    assert payload["doc_type"] == "ANNUAL_REPORT"
    assert payload["status"] == "QUEUED"
    assert payload["file_hash"] == hashlib.sha256(file_bytes).hexdigest()
    assert payload["file_size"] == len(file_bytes)
    assert isinstance(payload["task_id"], str)

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    fetch_payload = fetch_response.json()
    assert fetch_payload["task_id"] == payload["task_id"]
    assert fetch_payload["file_name"] == "report.pdf"

    uploads = test_app.state.object_storage_client.uploads
    assert len(uploads) == 1
    assert uploads[0].object_key == f"tasks/{payload['task_id']}/source/report.pdf"
    assert uploads[0].data == file_bytes
    assert uploads[0].content_type == "application/pdf"

    messages = test_app.state.queue_client.messages
    assert len(messages) == 1
    assert messages[0].task_id == payload["task_id"]
    assert messages[0].source_object_key == uploads[0].object_key
    assert messages[0].bucket == test_app.state.object_storage_client.bucket_name


async def test_duplicate_upload_reuses_existing_task(async_client, test_app) -> None:
    file_bytes = b"%PDF-1.7\nduplicate"
    first = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "IPO_PROSPECTUS"},
        files={"file": ("dup.pdf", file_bytes, "application/pdf")},
    )
    second = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "IPO_PROSPECTUS"},
        files={"file": ("dup.pdf", file_bytes, "application/pdf")},
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["task_id"] == first.json()["task_id"]
    assert len(test_app.state.object_storage_client.uploads) == 1
    assert len(test_app.state.queue_client.messages) == 1


async def test_failed_task_duplicate_upload_retries_dispatch(async_client, test_app) -> None:
    file_bytes = b"%PDF-1.7\nretry"
    test_app.state.queue_client.publish_failures_remaining = 1

    failed = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("retry.pdf", file_bytes, "application/pdf")},
    )

    assert failed.status_code == 503
    failed_payload = failed.json()
    assert failed_payload["code"] == "QUEUE_UNAVAILABLE"
    assert failed_payload["retryable"] is True
    assert failed_payload["task_id"]

    fetch_failed = await async_client.get(f"/api/v1/tasks/{failed_payload['task_id']}")
    assert fetch_failed.status_code == 200
    assert fetch_failed.json()["status"] == "FAILED"
    assert fetch_failed.json()["remark"] == "Failed to publish parser task message."

    retried = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("retry.pdf", file_bytes, "application/pdf")},
    )

    assert retried.status_code == 200
    retried_payload = retried.json()
    assert retried_payload["deduplicated"] is True
    assert retried_payload["task_id"] == failed_payload["task_id"]
    assert retried_payload["status"] == "QUEUED"
    assert retried_payload["remark"] is None
    assert len(test_app.state.object_storage_client.uploads) == 2
    assert len(test_app.state.queue_client.messages) == 1


async def test_storage_failure_marks_task_failed(async_client, test_app) -> None:
    test_app.state.object_storage_client.upload_failures_remaining = 1

    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "BOND_REPORT"},
        files={"file": ("storage-fail.pdf", b"%PDF-1.7\nstorage", "application/pdf")},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "OBJECT_STORAGE_UNAVAILABLE"
    assert payload["retryable"] is True
    assert payload["task_id"]

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    fetch_payload = fetch_response.json()
    assert fetch_payload["status"] == "FAILED"
    assert fetch_payload["remark"] == "Failed to store source PDF in object storage."
    assert len(test_app.state.queue_client.messages) == 0


async def test_empty_upload_returns_error(async_client) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "BOND_REPORT"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "INVALID_FILE_UPLOAD"
    assert payload["trace_id"]


async def test_missing_task_returns_not_found(async_client) -> None:
    response = await async_client.get("/api/v1/tasks/123456789012345678")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "TASK_NOT_FOUND"
    assert payload["task_id"] == "123456789012345678"
