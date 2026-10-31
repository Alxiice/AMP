"""Unit tests for services/streaming/registry.py — SegmentRegistry state machine."""

import threading
import time

from backend.services.streaming.registry import (
    Priority,
    SegmentRegistry,
    SegmentStatus,
    SegState,
    to_status,
)

K = ("dQw4w9WgXcQ", 3)


class TestRequest:
    def test_missing_is_queued(self):
        r = SegmentRegistry()
        assert r.get(K) == SegState.MISSING
        assert r.request(K, Priority.NORMAL, 0) is True
        assert r.get(K) == SegState.QUEUED

    def test_queued_same_or_worse_is_noop(self):
        r = SegmentRegistry()
        r.request(K, Priority.HIGH, 0)
        assert r.request(K, Priority.HIGH, 0) is False
        assert r.request(K, Priority.NORMAL, 0) is False
        assert r.request(K, Priority.CRITICAL, -1) is False  # older epoch

    def test_queued_better_priority_reranks(self):
        r = SegmentRegistry()
        r.request(K, Priority.NORMAL, 0)
        assert r.request(K, Priority.CRITICAL, 0) is True

    def test_queued_newer_epoch_reranks(self):
        r = SegmentRegistry()
        r.request(K, Priority.CRITICAL, 0)
        assert r.request(K, Priority.NORMAL, 1) is True

    def test_done_and_in_flight_are_noop(self):
        r = SegmentRegistry()
        r.mark_done(K)
        assert r.request(K, Priority.CRITICAL, 5) is False
        k2 = ("dQw4w9WgXcQ", 4)
        r.claim(k2)
        assert r.request(k2, Priority.CRITICAL, 5) is False

    def test_error_is_requeued(self):
        r = SegmentRegistry()
        r.claim(K)
        r.complete(K, False, "boom")
        assert r.error(K) == "boom"
        assert r.request(K, Priority.NORMAL, 0) is True
        assert r.error(K) is None


class TestClaim:
    def test_worker_claim_requires_current_item(self):
        r = SegmentRegistry()
        r.request(K, Priority.NORMAL, 0)
        r.request(K, Priority.CRITICAL, 1)
        assert r.claim(K, Priority.NORMAL, 0) is False  # superseded heap item
        assert r.claim(K, Priority.CRITICAL, 1) is True
        assert r.get(K) == SegState.IN_FLIGHT
        assert r.claim(K, Priority.CRITICAL, 1) is False  # duplicate item for the same key

    def test_sync_claim_jumps_queue(self):
        r = SegmentRegistry()
        r.request(K, Priority.NORMAL, 0)
        assert r.claim(K) is True
        assert r.claim(K, Priority.NORMAL, 0) is False  # the worker's item is now skipped

    def test_sync_claim_refuses_done_and_in_flight(self):
        r = SegmentRegistry()
        r.mark_done(K)
        assert r.claim(K) is False
        k2 = ("dQw4w9WgXcQ", 4)
        assert r.claim(k2) is True
        assert r.claim(k2) is False


class TestWaitAndLifecycle:
    def test_wait_wakes_on_complete(self):
        r = SegmentRegistry()
        r.claim(K)
        threading.Timer(0.1, r.complete, args=(K, True)).start()
        t0 = time.time()
        assert r.wait(K, 5) == SegState.DONE
        assert time.time() - t0 < 2

    def test_wait_times_out(self):
        r = SegmentRegistry()
        r.claim(K)
        assert r.wait(K, 0.05) == SegState.IN_FLIGHT

    def test_evicted_only_from_done(self):
        r = SegmentRegistry()
        r.mark_done(K)
        r.evicted(K)
        assert r.get(K) == SegState.MISSING
        r.claim(K)
        r.evicted(K)
        assert r.get(K) == SegState.IN_FLIGHT

    def test_unqueue_and_queued_songs(self):
        r = SegmentRegistry()
        r.request(("songAAAAAAA", 0), Priority.NORMAL, 0)
        r.request(("songBBBBBBB", 0), Priority.NORMAL, 0)
        r.claim(("songBBBBBBB", 1))
        assert sorted(r.queued_songs()) == ["songAAAAAAA", "songBBBBBBB"]
        assert r.unqueue("songBBBBBBB") == 1
        assert r.queued_songs() == ["songAAAAAAA"]
        assert r.get(("songBBBBBBB", 1)) == SegState.IN_FLIGHT

    def test_forget_keeps_in_flight(self):
        r = SegmentRegistry()
        r.mark_done(("dQw4w9WgXcQ", 0))
        r.claim(("dQw4w9WgXcQ", 1))
        r.forget("dQw4w9WgXcQ")
        assert r.snapshot("dQw4w9WgXcQ") == {1: SegState.IN_FLIGHT}

    def test_status_mapping(self):
        assert to_status(SegState.MISSING) == SegmentStatus.PENDING
        assert to_status(SegState.QUEUED) == SegmentStatus.PENDING
        assert to_status(SegState.IN_FLIGHT) == SegmentStatus.DOWNLOADING
        assert to_status(SegState.DONE) == SegmentStatus.DOWNLOADED
        assert to_status(SegState.ERROR) == SegmentStatus.ERROR
