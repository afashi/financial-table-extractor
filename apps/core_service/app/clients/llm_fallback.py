import asyncio
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from urllib import error, request

from pydantic import BaseModel, ValidationError

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.errors import LLMFallbackClientError
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.routing import RouteDecision

Sender = Callable[
    ...,
    Awaitable[dict[str, object]],
]


class LLMFallbackResponse(BaseModel):
    data_status: str
    table_data: dict[str, object] | None = None
    remark: str | None = None


class LLMFallbackClient:
    async def extract(
        self,
        *,
        rule: TableExtractionRule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        raise NotImplementedError

    async def dispose(self) -> None:
        return None


class DisabledLLMFallbackClient(LLMFallbackClient):
    async def extract(
        self,
        *,
        rule: TableExtractionRule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        del rule, decision
        return ExtractionOutcome(
            data_status="NOT_DISCLOSED",
            extraction_route="SLOW_TRACK",
            confidence_score=Decimal("88.00"),
            needs_review="0",
            remark="LLM fallback disabled; matched section did not contain a standard table.",
        )


class HttpLLMFallbackClient(LLMFallbackClient):
    def __init__(
        self,
        *,
        endpoint: str,
        model_name: str,
        timeout_seconds: float,
        api_key: str | None = None,
        sender: Sender | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        self._sender = sender

    async def extract(
        self,
        *,
        rule: TableExtractionRule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self._model_name,
            "target_table_code": rule.target_table_code,
            "target_table_name": rule.target_table_name,
            "context_blocks": decision.context_blocks,
            "matched_path": decision.matched_path,
        }

        try:
            response_payload = await self._send(
                endpoint=self._endpoint,
                payload=payload,
                headers=headers,
                timeout_seconds=self._timeout_seconds,
            )
            parsed = LLMFallbackResponse.model_validate(response_payload)
        except (ValidationError, LLMFallbackClientError) as exc:
            if isinstance(exc, LLMFallbackClientError):
                raise
            raise LLMFallbackClientError(
                "Failed to call LLM fallback endpoint.",
                reason=exc.__class__.__name__,
            ) from exc

        return ExtractionOutcome(
            data_status="SUCCESS" if parsed.data_status == "SUCCESS" else "NOT_DISCLOSED",
            extraction_route="SLOW_TRACK",
            table_data=parsed.table_data,
            confidence_score=Decimal("88.00"),
            needs_review="0",
            remark=parsed.remark or "LLM fallback completed.",
        )

    async def _send(
        self,
        *,
        endpoint: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, object]:
        if self._sender is not None:
            return await self._sender(
                endpoint=endpoint,
                payload=payload,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        return await asyncio.to_thread(
            self._send_blocking,
            endpoint,
            payload,
            headers,
            timeout_seconds,
        )

    def _send_blocking(
        self,
        endpoint: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        http_request = request.Request(
            url=endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            raise LLMFallbackClientError(
                "Failed to call LLM fallback endpoint.",
                reason=exc.__class__.__name__,
            ) from exc

        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise LLMFallbackClientError(
                "Failed to call LLM fallback endpoint.",
                reason=exc.__class__.__name__,
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMFallbackClientError(
                "Failed to call LLM fallback endpoint.",
                reason="InvalidResponseShape",
            )
        return parsed
