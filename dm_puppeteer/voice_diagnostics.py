"""
Voice receive diagnostics -- temporary instrumentation.

Logs per-user audio statistics to help diagnose why only
one player's portrait animates during Discord voice receive.

Drop this file after diagnosis is complete.
"""

import time
import threading
import logging
from collections import defaultdict
from pathlib import Path


# Set up file logger
_log_path = Path("data/voice_diagnostics.log")
_log_path.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("voice_diag")
logger.setLevel(logging.DEBUG)
_handler = logging.FileHandler(str(_log_path), mode="w", encoding="utf-8")
_handler.setFormatter(logging.Formatter(
    "%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_handler)


class VoiceDiagnostics:
    """Collects per-user audio statistics and dumps summaries periodically."""

    def __init__(self, dump_interval: float = 5.0):
        self._lock = threading.Lock()
        self._dump_interval = dump_interval
        self._last_dump = time.monotonic()

        # Per-user counters (keyed by whatever write() receives as user)
        self._raw_calls = defaultdict(int)        # total write() calls per user
        self._throttled = defaultdict(int)         # dropped by throttle
        self._processed = defaultdict(int)         # made it to process_audio
        self._rms_sum = defaultdict(float)         # sum of RMS values
        self._rms_max = defaultdict(float)         # peak RMS seen
        self._exceptions = defaultdict(list)       # exceptions caught per user
        self._unknown_users = defaultdict(int)     # user IDs not in processor map
        self._data_types = defaultdict(set)        # what type(data) we're seeing
        self._thresholds = {}                        # latest adaptive threshold per user

        # Global counters
        self._total_write_calls = 0
        self._total_queue_puts = 0

        # Snapshot of registered processors (for comparison)
        self._registered_ids = set()

    def set_registered_players(self, processor_keys):
        """Record which user IDs are registered in the sink."""
        with self._lock:
            self._registered_ids = set(processor_keys)
            logger.info(f"[REGISTERED] player IDs: {self._registered_ids}")
            logger.info(f"[REGISTERED] ID types: "
                        f"{[type(k).__name__ for k in self._registered_ids]}")

    def record_write_call(self, user_raw, user_id_resolved, data_raw):
        """Called at the top of write() BEFORE throttle check."""
        with self._lock:
            self._total_write_calls += 1
            key = user_id_resolved
            self._raw_calls[key] += 1
            self._data_types[key].add(type(data_raw).__name__)

            # Log the raw user object details on first sight
            if self._raw_calls[key] == 1:
                logger.info(
                    f"[NEW USER] raw_type={type(user_raw).__name__}, "
                    f"resolved_id={user_id_resolved} "
                    f"(type={type(user_id_resolved).__name__}), "
                    f"data_type={type(data_raw).__name__}, "
                    f"registered={user_id_resolved in self._registered_ids}")
                # Log all attributes of the user object for debugging
                if not isinstance(user_raw, int):
                    attrs = [a for a in dir(user_raw)
                             if not a.startswith('_')]
                    logger.info(f"[NEW USER] user object attrs: {attrs[:20]}")
                    for attr_name in ['id', 'user_id', 'name',
                                      'display_name', 'nick']:
                        val = getattr(user_raw, attr_name, '<MISSING>')
                        logger.info(
                            f"[NEW USER]   .{attr_name} = {val} "
                            f"(type={type(val).__name__})")

    def record_throttled(self, user_id):
        """Called when a frame is dropped by the throttle."""
        with self._lock:
            self._throttled[user_id] += 1

    def record_not_registered(self, user_id):
        """Called when user_id is not in self.processors."""
        with self._lock:
            self._unknown_users[user_id] += 1

    def record_processed(self, user_id, rms, threshold=0.0):
        """Called after successful process_audio()."""
        with self._lock:
            self._processed[user_id] += 1
            self._rms_sum[user_id] += rms
            if rms > self._rms_max[user_id]:
                self._rms_max[user_id] = rms
            self._thresholds[user_id] = threshold

    def record_queue_put(self):
        """Called when an event is put on the event queue."""
        with self._lock:
            self._total_queue_puts += 1

    def record_exception(self, user_id, exc):
        """Called when an exception is caught in write()."""
        with self._lock:
            self._exceptions[user_id].append(
                f"{type(exc).__name__}: {exc}")
            # Log exceptions immediately -- they're rare and important
            logger.warning(
                f"[EXCEPTION] user={user_id}: {type(exc).__name__}: {exc}")

    def maybe_dump(self):
        """Dump summary if interval has elapsed. Call from write()."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_dump < self._dump_interval:
                return
            self._dump_summary(now)
            self._last_dump = now

    def force_dump(self):
        """Force a summary dump (call on disconnect)."""
        with self._lock:
            self._dump_summary(time.monotonic())

    def _dump_summary(self, now):
        """Write summary to log. Must be called with lock held."""
        logger.info("=" * 60)
        logger.info(f"[SUMMARY] total write() calls: {self._total_write_calls}")
        logger.info(f"[SUMMARY] total queue puts: {self._total_queue_puts}")
        logger.info(f"[SUMMARY] registered IDs: {self._registered_ids}")

        all_users = (set(self._raw_calls.keys()) |
                     set(self._unknown_users.keys()))

        if not all_users:
            logger.info("[SUMMARY] No users seen yet")
            logger.info("=" * 60)
            return

        for uid in sorted(all_users, key=str):
            raw = self._raw_calls.get(uid, 0)
            throttled = self._throttled.get(uid, 0)
            processed = self._processed.get(uid, 0)
            unknown = self._unknown_users.get(uid, 0)
            avg_rms = (self._rms_sum.get(uid, 0) / processed
                       if processed > 0 else 0)
            peak = self._rms_max.get(uid, 0)
            dtypes = self._data_types.get(uid, set())
            errs = len(self._exceptions.get(uid, []))
            registered = uid in self._registered_ids

            logger.info(
                f"[USER {uid}] registered={registered} | "
                f"raw={raw} throttled={throttled} processed={processed} "
                f"unknown_drops={unknown} | "
                f"avg_rms={avg_rms:.4f} peak_rms={peak:.4f} "
                f"adaptive_threshold={self._thresholds.get(uid, 0):.4f} | "
                f"data_types={dtypes} errors={errs}")

        logger.info("=" * 60)

        # Reset counters for next interval
        self._raw_calls.clear()
        self._throttled.clear()
        self._processed.clear()
        self._rms_sum.clear()
        self._rms_max.clear()
        self._unknown_users.clear()
        self._exceptions.clear()
        self._total_write_calls = 0
        self._total_queue_puts = 0
        # DON'T clear _registered_ids or _data_types


# Global instance
diag = VoiceDiagnostics(dump_interval=5.0)
