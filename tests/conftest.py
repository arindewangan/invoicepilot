import os
import sys

# make top-level modules importable regardless of how pytest is invoked
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store


def _isolated_store(tmp_path, monkeypatch):
    """Point the JSON store at a temp file for test isolation."""
    target = tmp_path / "invoices.json"
    monkeypatch.setattr(store, "_path", lambda: str(target))
    store.clear()
    return store
