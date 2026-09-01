"""Shared fixtures: a Config wired to the repo's real config.example.yaml +
taxonomy.yaml, and a SQLite-backed store in a temp dir (no real warehouse needed)."""
import pytest

from helpers import make_cfg, make_store


@pytest.fixture
def cfg(tmp_path):
    return make_cfg(tmp_path)


@pytest.fixture
def store(tmp_path):
    return make_store(tmp_path)
