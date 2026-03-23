import hashlib


async def test_create_and_fetch_task(async_client) -> None:
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

    fetch_response = await async_client.get(f"/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    fetch_payload = fetch_response.json()
    assert fetch_payload["task_id"] == payload["task_id"]
    assert fetch_payload["file_name"] == "report.pdf"


async def test_duplicate_upload_reuses_existing_task(async_client) -> None:
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
    response = await async_client.get("/tasks/123456789012345678")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "TASK_NOT_FOUND"
    assert payload["task_id"] == "123456789012345678"
