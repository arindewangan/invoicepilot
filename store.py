"""Tiny JSON-file store for invoices created through InvoicePilot."""
import json
import os
from threading import Lock

_lock = Lock()


def _path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "data", "invoices.json")


def _read() -> list:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write(rows: list) -> None:
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def save_invoice(record: dict) -> dict:
    with _lock:
        rows = _read()
        rows = [r for r in rows if r.get("id") != record.get("id")]
        rows.insert(0, record)
        _write(rows)
    return record


def list_invoices() -> list:
    with _lock:
        return _read()


def get_invoice_record(invoice_id: str):
    with _lock:
        for r in _read():
            if r.get("id") == invoice_id:
                return r
    return None


def clear() -> None:
    """Used by tests / demo seeding."""
    with _lock:
        _write([])
