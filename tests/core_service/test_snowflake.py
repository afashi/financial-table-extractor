from apps.shared.utils.snowflake import SnowflakeIdGenerator


def test_snowflake_ids_are_unique_and_sorted() -> None:
    generator = SnowflakeIdGenerator(worker_id=3, epoch_ms=1735689600000)

    ids = [generator.next_id() for _ in range(128)]

    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
