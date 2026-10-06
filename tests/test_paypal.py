"""Tests for the PayPal client (demo mode + mocked live sandbox calls)."""
import paypal_client
from paypal_client import PayPalClient


def _demo_client(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    return PayPalClient()


def test_demo_mode_when_no_credentials(monkeypatch):
    c = _demo_client(monkeypatch)
    assert c.demo is True
    assert c.mode == "demo"
    assert "simulat" in c.mode_label().lower()


def test_demo_create_send_status_cycle(monkeypatch):
    c = _demo_client(monkeypatch)
    created = c.create_invoice({
        "recipient": "Acme Corp", "amount": 800.0, "currency": "USD",
        "description": "Logo work", "due_date": "2026-10-10",
    })
    assert created["id"].startswith("DEMO-INV-")
    assert created["status"] == "DRAFT"
    assert created["demo"] is True

    sent = c.send_invoice(created["id"])
    assert sent["status"] == "SENT"
    assert "simulated" in sent["payment_url"]

    detail = c.get_invoice(created["id"])
    assert detail["status"] == "SENT"

    paid = c.simulate_payment(created["id"])
    assert paid["status"] == "PAID"
    assert c.get_invoice(created["id"])["status"] == "PAID"


def test_demo_unknown_invoice_raises(monkeypatch):
    c = _demo_client(monkeypatch)
    try:
        c.send_invoice("DEMO-INV-NOPE")
        raise AssertionError("should have raised")
    except ValueError:
        pass


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _live_client(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test-id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "test-secret")
    return PayPalClient()


def test_live_mode_uses_sandbox_token_and_invoicing_api(monkeypatch):
    c = _live_client(monkeypatch)
    assert c.demo is False
    assert c.mode == "sandbox"

    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if url.endswith("/v1/oauth2/token"):
            return _FakeResp({"access_token": "tok123"})
        if url.endswith("/v2/invoicing/invoices"):
            body = kwargs["json"]
            assert body["detail"]["currency_code"] == "USD"
            assert body["items"][0]["unit_amount"]["value"] == "800.00"
            return _FakeResp({"id": "INV2-TEST-1", "status": "DRAFT"})
        if url.endswith("/send"):
            return _FakeResp({})
        raise AssertionError(f"unexpected POST {url}")

    def fake_get(url, **kwargs):
        calls.append(url)
        return _FakeResp({
            "id": "INV2-TEST-1", "status": "SENT",
            "links": [{"rel": "payer-view", "href": "https://www.sandbox.paypal.com/invoice/p/INV2-TEST-1"}],
        })

    monkeypatch.setattr(paypal_client.requests, "post", fake_post)
    monkeypatch.setattr(paypal_client.requests, "get", fake_get)

    created = c.create_invoice({
        "recipient": "Acme Corp", "email": "billing@acme.example", "amount": 800,
        "currency": "USD", "description": "Logo work", "due_date": "2026-10-10",
    })
    assert created["id"] == "INV2-TEST-1"
    assert created["demo"] is False

    sent = c.send_invoice("INV2-TEST-1")
    assert sent["status"] == "SENT"
    assert sent["payment_url"] == "https://www.sandbox.paypal.com/invoice/p/INV2-TEST-1"

    assert any("oauth2/token" in u for u in calls)
    assert any("sandbox.paypal.com" in u for u in calls)
