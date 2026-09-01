"""SQLStore behaviour against a real database (SQLite), plus the coercion helpers.

These run against an actual SQLAlchemy engine rather than a mock, so dtype
round-tripping and write-then-read visibility are genuinely exercised.
"""
import pandas as pd

from hire_pipeline.store import truthy, to_float

from helpers import make_store


def test_write_read_roundtrip(store):
    df = pd.DataFrame([{"interaction_id": "i1", "x": 1},
                       {"interaction_id": "i2", "x": 2}])
    assert store.write("t", df) == 2
    out = store.read("t")
    assert list(out["interaction_id"]) == ["i1", "i2"]
    assert list(out["x"]) == [1, 2]


def test_has_and_missing_table(store):
    assert not store.has("nope")
    assert store.read("nope").empty          # must not raise
    store.write("yes", pd.DataFrame([{"a": 1}]))
    assert store.has("yes")


def test_append_creates_and_extends(store):
    assert store.append("t", [{"interaction_id": "i1"}]) == 1
    assert store.append("t", [{"interaction_id": "i2"}, {"interaction_id": "i3"}]) == 2
    assert store.append("t", []) == 0
    assert len(store.read("t")) == 3


def test_write_replaces_rather_than_appends(store):
    store.write("t", pd.DataFrame([{"interaction_id": "i1"}]))
    store.write("t", pd.DataFrame([{"interaction_id": "i2"}]))
    assert store.ids("t") == {"i2"}          # full refresh, not accumulation


def test_ids(store):
    store.write("t", pd.DataFrame([
        {"interaction_id": "i1", "status": "auto"},
        {"interaction_id": "i2", "status": "escalate"},
    ]))
    assert store.ids("t") == {"i1", "i2"}
    assert store.ids("missing") == set()


def test_awkward_table_names_work_end_to_end(store):
    """Users may rename tables to anything; a leading digit is invalid unquoted."""
    name = "00_raw_agent_interactions"
    store.write(name, pd.DataFrame([{"interaction_id": "i1", "turn": 1}]))
    assert store.has(name)
    assert store.ids(name) == {"i1"}
    assert len(store.read(name)) == 1
    store.append(name, [{"interaction_id": "i2", "turn": 2}])
    assert store.ids(name) == {"i1", "i2"}
    store.write(name, pd.DataFrame([{"interaction_id": "i3", "turn": 3}]))
    assert store.ids(name) == {"i3"}


def test_persists_across_store_instances(tmp_path):
    """A second run must see the previous run's tables — the point of a database."""
    a = make_store(tmp_path)
    a.write("t", pd.DataFrame([{"interaction_id": "i1"}]))
    b = make_store(tmp_path)                 # new engine, same database file
    assert b.ids("t") == {"i1"}


def test_booleans_survive_a_database_roundtrip(store):
    """SQLite has no boolean type; truthy() is what makes the flags usable again."""
    store.write("t", pd.DataFrame([{"interaction_id": "i1", "resolved": True},
                                   {"interaction_id": "i2", "resolved": False}]))
    values = store.read("t")["resolved"].tolist()
    assert [truthy(v) for v in values] == [True, False]


def test_truthy_handles_database_representations():
    assert truthy(True) and truthy(1) and truthy("True") and truthy("1")
    assert not truthy(False) and not truthy(0)
    assert not truthy("False") and not truthy("nan") and not truthy(None)


def test_writing_a_columnless_frame_is_refused_clearly(store):
    """to_sql would emit `CREATE TABLE x ()` and fail in the driver. Reachable for
    real: a step whose groupby produced no rows builds exactly this frame."""
    import pytest
    with pytest.raises(ValueError) as e:
        store.write("t", pd.DataFrame())
    assert "no columns" in str(e.value)


def test_to_float_coercion():
    assert to_float("0.7") == 0.7
    assert to_float(None) == 0.0
    assert to_float("not-a-number", default=0.5) == 0.5
