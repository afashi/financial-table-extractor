import asyncio
from collections.abc import Sequence
from typing import Any


class EmbeddingClient:
    async def encode(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class BGEM3EmbeddingClient(EmbeddingClient):
    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-m3",
        use_fp16: bool = True,
        model: Any = None,
    ) -> None:
        self._model = model or _build_model(model_name=model_name, use_fp16=use_fp16)

    async def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode_blocking, list(texts))

    def _encode_blocking(self, texts: list[str]) -> list[list[float]]:
        output = self._model.encode(texts, batch_size=8, max_length=8192)
        return [list(map(float, row)) for row in output["dense_vecs"]]


def _build_model(*, model_name: str, use_fp16: bool):
    from FlagEmbedding import BGEM3FlagModel

    return BGEM3FlagModel(model_name, use_fp16=use_fp16)
