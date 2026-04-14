from dataclasses import dataclass

from apps.core_service.app.clients.embedding import BGEM3EmbeddingClient
from apps.core_service.app.vector_sync import sync_rule_vectors


class FakeModel:
    def encode(self, texts, batch_size, max_length):
        del batch_size, max_length
        assert texts == ["主营业务分析", "其他章节"]
        return {"dense_vecs": [[1.0, 0.0], [0.0, 1.0]]}


async def test_bge_m3_client_returns_dense_vectors() -> None:
    client = BGEM3EmbeddingClient(model=FakeModel())

    vectors = await client.encode(["主营业务分析", "其他章节"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


@dataclass
class FakeRule:
    id: int
    semantic_anchor_text: str | None
    target_table_name: str
    semantic_vector: list[float] | None = None


class FakeRuleRepository:
    def __init__(self) -> None:
        self.rules = [
            FakeRule(
                id=1,
                semantic_anchor_text="主营业务分部收入表",
                target_table_name="主营业务分部收入",
            )
        ]

    async def list_rules_missing_vectors(self, session):
        del session
        return [rule for rule in self.rules if rule.semantic_vector is None]

    async def update_semantic_vectors(self, session, *, pairs):
        del session
        for rule, vector in pairs:
            rule.semantic_vector = vector


class FakeEmbeddingClient:
    def __init__(self, vectors) -> None:
        self._vectors = vectors

    async def encode(self, texts):
        assert texts == ["主营业务分部收入表"]
        return self._vectors


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


async def test_sync_rule_vectors_updates_missing_vectors() -> None:
    repository = FakeRuleRepository()
    session = FakeSession()

    count = await sync_rule_vectors(
        session=session,
        rule_repository=repository,
        embedding_client=FakeEmbeddingClient([[1.0, 0.0]]),
    )

    assert count == 1
    assert repository.rules[0].semantic_vector == [1.0, 0.0]
    assert session.commit_count == 1
