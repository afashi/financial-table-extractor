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
        self._model = model
        self._model_name = model_name
        self._use_fp16 = use_fp16

    async def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode_blocking, list(texts))

    def _encode_blocking(self, texts: list[str]) -> list[list[float]]:
        output = self._get_model().encode(texts, batch_size=8, max_length=8192)
        return [list(map(float, row)) for row in output["dense_vecs"]]

    def _get_model(self):
        if self._model is None:
            self._model = _build_model(
                model_name=self._model_name,
                use_fp16=self._use_fp16,
            )
        return self._model


def _build_model(*, model_name: str, use_fp16: bool):
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "FlagEmbedding is required to encode semantic vectors. Install it before running vector sync or vector-enhanced routing."
        ) from exc

    return BGEM3FlagModel(model_name, use_fp16=use_fp16)
