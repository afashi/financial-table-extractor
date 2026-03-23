import threading
import time


class SnowflakeIdGenerator:
    """A minimal Snowflake-style BIGINT generator for public task IDs."""

    worker_id_bits = 10
    sequence_bits = 12
    max_worker_id = (1 << worker_id_bits) - 1
    sequence_mask = (1 << sequence_bits) - 1

    def __init__(self, *, worker_id: int, epoch_ms: int) -> None:
        if worker_id < 0 or worker_id > self.max_worker_id:
            raise ValueError(
                f"worker_id must be between 0 and {self.max_worker_id}, got {worker_id}.",
            )

        self._worker_id = worker_id
        self._epoch_ms = epoch_ms
        self._sequence = 0
        self._last_timestamp = -1
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            timestamp = self._current_timestamp()
            if timestamp < self._last_timestamp:
                raise ValueError("System clock moved backwards; cannot generate Snowflake ID.")

            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & self.sequence_mask
                if self._sequence == 0:
                    timestamp = self._wait_for_next_millisecond(timestamp)
            else:
                self._sequence = 0

            self._last_timestamp = timestamp
            return (
                ((timestamp - self._epoch_ms) << (self.worker_id_bits + self.sequence_bits))
                | (self._worker_id << self.sequence_bits)
                | self._sequence
            )

    @staticmethod
    def _current_timestamp() -> int:
        return int(time.time() * 1000)

    def _wait_for_next_millisecond(self, current_timestamp: int) -> int:
        timestamp = self._current_timestamp()
        while timestamp <= current_timestamp:
            timestamp = self._current_timestamp()
        return timestamp
