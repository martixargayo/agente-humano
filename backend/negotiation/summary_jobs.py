from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Set, Tuple

from state import SessionState, get_session_state, save_session_state

from .context_utils import maybe_refresh_summary, slice_last_user_turns
from .state.deps import AgentDeps


JobKey = Tuple[str, str, int]
SessionKey = Tuple[str, str]


@dataclass(frozen=True)
class SummaryRefreshJob:
    user_id: str
    session_id: str
    turn_id: int
    expected_turn_count: int
    context_limit_turns: int
    keep_last_n_turns: int


class DeferredSummaryManager:
    def __init__(self, *, max_processed_keys: int | None = None) -> None:
        self._queue: Deque[SummaryRefreshJob] = deque()
        self._queue_lock = threading.Lock()
        self._queue_event = threading.Event()
        self._session_locks: Dict[SessionKey, threading.Lock] = {}
        self._session_locks_guard = threading.Lock()
        self._processed_keys: Set[JobKey] = set()
        self._processed_order: Deque[JobKey] = deque()
        self._inflight_keys: Set[JobKey] = set()
        self._worker: Optional[threading.Thread] = None
        self._stop = False
        max_env = int(os.getenv("NEGOTIATION_SUMMARY_JOB_IDEMPOTENCY_MAX", "5000"))
        self._max_processed_keys = max_processed_keys if max_processed_keys is not None else max_env

    def _job_key(self, job: SummaryRefreshJob) -> JobKey:
        return (job.user_id, job.session_id, job.turn_id)

    def _get_session_lock(self, user_id: str, session_id: str) -> threading.Lock:
        key = (user_id, session_id)
        with self._session_locks_guard:
            lock = self._session_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._session_locks[key] = lock
            return lock

    def _remember_processed(self, job_key: JobKey) -> None:
        self._processed_keys.add(job_key)
        self._processed_order.append(job_key)
        while len(self._processed_order) > self._max_processed_keys:
            old_key = self._processed_order.popleft()
            self._processed_keys.discard(old_key)

    def start_worker(self, deps: AgentDeps) -> None:
        if self._worker is not None and self._worker.is_alive():
            return

        self._stop = False

        def _run() -> None:
            while not self._stop:
                self._queue_event.wait(timeout=0.2)
                self._queue_event.clear()
                self.drain_queue(deps=deps, max_jobs=1)

        self._worker = threading.Thread(target=_run, name="summary-refresh-worker", daemon=True)
        self._worker.start()

    def stop_worker(self) -> None:
        self._stop = True
        self._queue_event.set()
        if self._worker is not None:
            self._worker.join(timeout=1.0)

    def enqueue(self, job: SummaryRefreshJob) -> bool:
        job_key = self._job_key(job)
        with self._queue_lock:
            if job_key in self._processed_keys or job_key in self._inflight_keys:
                return False
            self._inflight_keys.add(job_key)
            self._queue.append(job)
        self._queue_event.set()
        return True

    def run_job_sync(self, job: SummaryRefreshJob, *, deps: AgentDeps) -> dict:
        session_lock = self._get_session_lock(job.user_id, job.session_id)
        with session_lock:
            state = get_session_state(job.user_id, job.session_id)
            meta = dict(getattr(state, "summary_meta", {}) or {})
            last_refresh_turn_id = int(meta.get("last_refresh_turn_id") or 0)
            if last_refresh_turn_id >= job.turn_id:
                return {"job_status": "stale_last_refresh", "turn_id": job.turn_id}

            # Guard opcional: si la sesión avanzó mucho, no aplicar trabajo antiguo.
            if state.turn_count > job.expected_turn_count:
                return {
                    "job_status": "stale_turn_count",
                    "turn_id": job.turn_id,
                    "expected_turn_count": job.expected_turn_count,
                    "actual_turn_count": state.turn_count,
                }

            refresh_meta = maybe_refresh_summary(
                state,
                deps=deps,
                context_limit_turns=job.context_limit_turns,
                keep_last_n_turns=job.keep_last_n_turns,
            )
            meta["last_refresh_turn_id"] = job.turn_id
            meta["last_refresh_turn_count"] = state.turn_count
            meta["last_job_status"] = "applied" if refresh_meta.get("refreshed") else "skipped"
            state.summary_meta = meta
            save_session_state(state)
            return {"job_status": "applied", "refresh_meta": refresh_meta, "turn_id": job.turn_id}

    def _run_next_job(self, *, deps: AgentDeps) -> Optional[dict]:
        with self._queue_lock:
            if not self._queue:
                return None
            job = self._queue.popleft()

        try:
            return self.run_job_sync(job, deps=deps)
        finally:
            job_key = self._job_key(job)
            with self._queue_lock:
                self._inflight_keys.discard(job_key)
                self._remember_processed(job_key)

    def drain_queue(self, *, deps: AgentDeps, max_jobs: Optional[int] = None) -> int:
        processed = 0
        while True:
            if max_jobs is not None and processed >= max_jobs:
                return processed
            result = self._run_next_job(deps=deps)
            if result is None:
                return processed
            processed += 1

    def idempotency_stats(self) -> dict:
        with self._queue_lock:
            return {
                "processed_keys": len(self._processed_keys),
                "processed_order": len(self._processed_order),
                "inflight_keys": len(self._inflight_keys),
                "queue_len": len(self._queue),
            }


SUMMARY_JOBS = DeferredSummaryManager()


def deferred_summary_enabled() -> bool:
    return os.getenv("NEGOTIATION_DEFER_SUMMARY", "0") == "1"


def make_turn_job(
    state: SessionState,
    *,
    context_limit_turns: int,
    keep_last_n_turns: int,
) -> SummaryRefreshJob:
    return SummaryRefreshJob(
        user_id=state.user_id,
        session_id=state.session_id,
        turn_id=state.turn_count,
        expected_turn_count=state.turn_count,
        context_limit_turns=context_limit_turns,
        keep_last_n_turns=keep_last_n_turns,
    )


def apply_deferred_hard_trim(state: SessionState, *, max_user_turns: int) -> bool:
    if max_user_turns <= 0:
        return False
    suffix = slice_last_user_turns(state.history, max_user_turns)
    if len(suffix) >= len(state.history):
        return False
    state.history = suffix
    return True
