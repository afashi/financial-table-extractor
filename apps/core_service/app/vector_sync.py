async def sync_rule_vectors(*, session, rule_repository, embedding_client) -> int:
    rules = await rule_repository.list_rules_missing_vectors(session)
    if not rules:
        return 0

    texts = [rule.semantic_anchor_text or rule.target_table_name for rule in rules]
    vectors = await embedding_client.encode(texts)
    await rule_repository.update_semantic_vectors(
        session,
        pairs=list(zip(rules, vectors, strict=True)),
    )
    await session.commit()
    return len(rules)
