"""
tests/test_job_queue.py
-----------------------
Unit tests for the SQLite-backed durable job queue (executor/job_queue.py).

Tests run against a fresh in-memory-like DB by monkey-patching DB_PATH to a
tmp path so the real data/queue.db is never touched.
"""

import os
import tempfile
from pathlib import Path

import pytest

# ── patch DB_PATH before the module caches its connection ──────────────────────
_tmp_dir = tempfile.mkdtemp()
_test_db = Path(_tmp_dir) / "test_queue.db"

import executor.job_queue as jq

# Redirect to temp DB for tests
jq.DB_PATH = _test_db
if hasattr(jq._local, "conn"):
    jq._local.conn = None  # force reconnect on next use
jq.init_db()  # create table in temp DB


def _fresh_job_id(suffix: str = "") -> str:
    import uuid
    return f"test_{uuid.uuid4().hex[:8]}{suffix}"


# ── enqueue ────────────────────────────────────────────────────────────────────

def test_enqueue_returns_row_id():
    job_id = _fresh_job_id()
    row_id = jq.enqueue(job_id, "ACC-0000-0001")
    assert isinstance(row_id, int)
    assert row_id > 0


def test_enqueue_idempotent():
    """Enqueueing the same job_id twice should return the existing row ID."""
    job_id = _fresh_job_id()
    id1 = jq.enqueue(job_id, "ACC-0000-0002")
    id2 = jq.enqueue(job_id, "ACC-0000-0002")
    assert id1 == id2


def test_enqueue_initial_state_is_queued():
    job_id = _fresh_job_id()
    jq.enqueue(job_id, "ACC-0000-0003")
    record = jq.get_job(job_id)
    assert record is not None
    assert record["state"] == jq.QUEUED


# ── transition ─────────────────────────────────────────────────────────────────

def test_transition_dispatched():
    job_id = _fresh_job_id()
    jq.enqueue(job_id, "ACC-0000-0010")
    ok = jq.transition(job_id, jq.DISPATCHED)
    assert ok is True
    assert jq.get_job(job_id)["state"] == jq.DISPATCHED


def test_transition_running():
    job_id = _fresh_job_id()
    jq.enqueue(job_id, "ACC-0000-0011")
    jq.transition(job_id, jq.DISPATCHED)
    jq.transition(job_id, jq.RUNNING)
    assert jq.get_job(job_id)["state"] == jq.RUNNING


def test_transition_completed():
    job_id = _fresh_job_id()
    jq.enqueue(job_id, "ACC-0000-0012")
    jq.transition(job_id, jq.DISPATCHED)
    jq.transition(job_id, jq.RUNNING)
    jq.transition(job_id, jq.COMPLETED)
    assert jq.get_job(job_id)["state"] == jq.COMPLETED


def test_transition_failed_with_error_msg():
    job_id = _fresh_job_id()
    jq.enqueue(job_id, "ACC-0000-0013")
    jq.transition(job_id, jq.FAILED, error_msg="container crash")
    record = jq.get_job(job_id)
    assert record["state"] == jq.FAILED
    assert record["error_msg"] == "container crash"


def test_transition_nonexistent_job_returns_false():
    ok = jq.transition("does_not_exist", jq.COMPLETED)
    assert ok is False


# ── list_jobs ──────────────────────────────────────────────────────────────────

def test_list_jobs_by_state():
    j1 = _fresh_job_id("_completed")
    j2 = _fresh_job_id("_completed")
    jq.enqueue(j1, "ACC-FFFF-0001")
    jq.enqueue(j2, "ACC-FFFF-0002")
    jq.transition(j1, jq.COMPLETED)
    jq.transition(j2, jq.COMPLETED)

    completed = [r for r in jq.list_jobs(state=jq.COMPLETED) if r["job_id"] in {j1, j2}]
    assert len(completed) == 2


# ── queue_position ─────────────────────────────────────────────────────────────

def test_queue_position_ordering():
    jobs = [_fresh_job_id("_pos") for _ in range(3)]
    for j in jobs:
        jq.enqueue(j, "ACC-0000-0020")

    # All three should be QUEUED; positions relative to insertion order
    pos_values = [jq.queue_position(j) for j in jobs]
    assert pos_values == sorted(pos_values)   # positions are monotonically increasing


def test_queue_position_zero_if_not_queued():
    job_id = _fresh_job_id("_pos_nq")
    jq.enqueue(job_id, "ACC-0000-0021")
    jq.transition(job_id, jq.RUNNING)
    assert jq.queue_position(job_id) == 0


# ── pending_count ──────────────────────────────────────────────────────────────

def test_pending_count_increases():
    before = jq.pending_count()
    j = _fresh_job_id("_pending")
    jq.enqueue(j, "ACC-0000-0030")
    assert jq.pending_count() == before + 1


def test_pending_count_decreases_after_transition():
    j = _fresh_job_id("_pending2")
    jq.enqueue(j, "ACC-0000-0031")
    before = jq.pending_count()
    jq.transition(j, jq.RUNNING)
    assert jq.pending_count() == before - 1


# ── crash recovery ─────────────────────────────────────────────────────────────

def test_get_recoverable_jobs():
    """QUEUED and DISPATCHED jobs must appear in the recovery list."""
    j_queued = _fresh_job_id("_rec_q")
    j_dispatched = _fresh_job_id("_rec_d")
    j_running = _fresh_job_id("_rec_r")
    j_completed = _fresh_job_id("_rec_c")

    jq.enqueue(j_queued, "ACC-RECOV-0001")
    jq.enqueue(j_dispatched, "ACC-RECOV-0002")
    jq.enqueue(j_running, "ACC-RECOV-0003")
    jq.enqueue(j_completed, "ACC-RECOV-0004")

    jq.transition(j_dispatched, jq.DISPATCHED)
    jq.transition(j_running, jq.RUNNING)
    jq.transition(j_completed, jq.COMPLETED)

    recoverable_ids = {r["job_id"] for r in jq.get_recoverable_jobs()}

    assert j_queued in recoverable_ids
    assert j_dispatched in recoverable_ids
    # RUNNING is intentionally recoverable too (server may have died mid-run)
    # — our recovery marks them FAILED
    assert j_completed not in recoverable_ids
