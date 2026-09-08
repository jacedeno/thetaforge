"""Equity curve sampling — slot flooring, idempotency, and backfill priority."""

from datetime import datetime, timedelta, timezone

from agent.journal import connect, record_equity, slot_floor


def utc(h, m, s=0):
    return datetime(2026, 9, 8, h, m, s, tzinfo=timezone.utc)


def rows(con):
    return [(r["ts"], r["equity"], r["source"])
            for r in con.execute("SELECT * FROM equity_samples ORDER BY ts")]


def test_slot_floor_snaps_to_the_five_minute_bar():
    assert slot_floor(utc(14, 37, 52)) == utc(14, 35)
    assert slot_floor(utc(14, 35, 0)) == utc(14, 35)
    assert slot_floor(utc(14, 39, 59)) == utc(14, 35)
    assert slot_floor(utc(14, 40, 0)) == utc(14, 40)


def test_same_slot_rewrites_instead_of_stacking(tmp_path):
    """A restart inside one bar must not leave two points on the curve."""
    con = connect(tmp_path / "t.db")
    record_equity(3000.0, when=utc(14, 36), con=con)
    record_equity(3010.0, when=utc(14, 38), con=con)
    assert rows(con) == [("2026-09-08T14:35:00+00:00", 3010.0, "loop")]


def test_distinct_slots_accumulate(tmp_path):
    con = connect(tmp_path / "t.db")
    for i in range(4):
        record_equity(3000.0 + i, when=utc(14, 0) + timedelta(minutes=5 * i), con=con)
    assert [r[1] for r in rows(con)] == [3000.0, 3001.0, 3002.0, 3003.0]


def test_backfill_never_overwrites_a_loop_sample(tmp_path):
    """The loop records the number the sizing ladder saw; it outranks a bucket."""
    con = connect(tmp_path / "t.db")
    record_equity(3000.0, when=utc(14, 36), source="loop", con=con)
    record_equity(9999.0, when=utc(14, 36), source="backfill", con=con)
    assert rows(con) == [("2026-09-08T14:35:00+00:00", 3000.0, "loop")]


def test_loop_sample_replaces_a_backfilled_one(tmp_path):
    con = connect(tmp_path / "t.db")
    record_equity(9999.0, when=utc(14, 36), source="backfill", con=con)
    record_equity(3000.0, when=utc(14, 36), source="loop", con=con)
    assert rows(con) == [("2026-09-08T14:35:00+00:00", 3000.0, "loop")]


def test_backfill_is_idempotent(tmp_path):
    con = connect(tmp_path / "t.db")
    for _ in range(3):
        record_equity(2900.0, when=utc(14, 36), source="backfill", con=con)
    assert len(rows(con)) == 1
