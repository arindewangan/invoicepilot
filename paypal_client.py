"""PayPal REST client for InvoicePilot.

Talks to the PayPal SANDBOX (https://api-m.sandbox.paypal.com) using the
official Invoicing API v2. Credentials come from env vars only:
    PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET

When credentials are absent the client runs in clearly-labelled SHOWCASE
(demo) MODE: invoices are simulated in-memory and NO real transaction,
draft, or send ever happens. Nothing is faked as real.
"""
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import requests

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"


class PayPalClient:
    def __init__(self):
        self.client_id = (os.environ.get("PAYPAL_CLIENT_ID") or "").strip()
        self.client_secret = (os.environ.get("PAYPAL_CLIENT_SECRET") or "").strip()
        self.demo = not (self.client_id and self.client_secret)
        self._token = None
        # demo-mode in-memory store: invoice_id -> invoice dict
        self._demo_invoices = {}

    # ------------------------------------------------------------------ mode
    @property
    def mode(self) -> str:
        return "demo" if self.demo else "sandbox"

    def mode_label(self) -> str:
        if self.demo:
            return "Showcase mode — simulated, no real money moves"
        return "PayPal Sandbox (live test API)"

    # ------------------------------------------------------------------ auth
    def _get_token(self) -> str:
        if self._token:
            return self._token
        resp = requests.post(
            f"{SANDBOX_BASE}/v1/oauth2/token",
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            timeout=20,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": str(uuid.uuid4()),
        }

    # ---------------------------------------------------------------- create
    def create_invoice(self, draft: dict) -> dict:
        """Create a DRAFT invoice. Returns {'id', 'status', 'links'|'payment_url', 'raw'}."""
        if self.demo:
            inv_id = f"DEMO-INV-{uuid.uuid4().hex[:8].upper()}"
            invoice = {
                "id": inv_id,
                "number": f"DEMO-{len(self._demo_invoices) + 1:04d}",
                "status": "DRAFT",
                "recipient": draft.get("recipient"),
                "email": draft.get("email"),
                "amount": draft.get("amount"),
                "currency": draft.get("currency", "USD"),
                "description": draft.get("description"),
                "due_date": draft.get("due_date"),
                "created": _now_iso(),
                "demo": True,
            }
            self._demo_invoices[inv_id] = invoice
            return {
                "id": inv_id,
                "status": "DRAFT",
                "payment_url": f"https://www.sandbox.paypal.com/invoice/p/{inv_id} (simulated)",
                "demo": True,
                "raw": invoice,
            }

        payload = {
            "detail": {
                "currency_code": draft.get("currency", "USD"),
                "note": draft.get("memo") or draft.get("description") or "",
                "invoice_date": date.today().isoformat(),
                "payment_term": {"term_type": "NET_7"},
            },
            "primary_recipients": [
                {
                    "billing_info": {
                        "business_name": draft.get("recipient") or "Client",
                        **({"email_address": draft["email"]} if draft.get("email") else {}),
                    }
                }
            ],
            "items": [
                {
                    "name": draft.get("description") or "Services rendered",
                    "quantity": "1",
                    "unit_amount": {
                        "currency_code": draft.get("currency", "USD"),
                        "value": f"{float(draft.get('amount', 0)):.2f}",
                    },
                }
            ],
        }
        if draft.get("due_date"):
            payload["detail"]["due_date"] = draft["due_date"]
        resp = requests.post(
            f"{SANDBOX_BASE}/v2/invoicing/invoices",
            headers=self._headers(),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
        inv_id = body["id"]
        return {
            "id": inv_id,
            "status": body.get("status", "DRAFT"),
            "demo": False,
            "raw": body,
        }

    # ------------------------------------------------------------------- send
    def send_invoice(self, invoice_id: str) -> dict:
        """Send the invoice to the recipient. Returns {'id', 'status', 'payment_url'}."""
        if self.demo:
            inv = self._demo_invoices.get(invoice_id)
            if not inv:
                raise ValueError(f"Unknown demo invoice {invoice_id}")
            inv["status"] = "SENT"
            inv["sent_at"] = _now_iso()
            return {
                "id": invoice_id,
                "status": "SENT",
                "payment_url": f"https://www.sandbox.paypal.com/invoice/p/{invoice_id} (simulated)",
                "demo": True,
            }
        resp = requests.post(
            f"{SANDBOX_BASE}/v2/invoicing/invoices/{invoice_id}/send",
            headers=self._headers(),
            json={},
            timeout=20,
        )
        resp.raise_for_status()
        detail = self.get_invoice(invoice_id)
        url = next(
            (l.get("href") for l in detail["raw"].get("links", []) if l.get("rel") == "payer-view"),
            None,
        )
        return {"id": invoice_id, "status": "SENT", "payment_url": url, "demo": False}

    # ----------------------------------------------------------------- status
    def get_invoice(self, invoice_id: str) -> dict:
        """Fetch current invoice details/status."""
        if self.demo:
            inv = self._demo_invoices.get(invoice_id)
            if not inv:
                raise ValueError(f"Unknown demo invoice {invoice_id}")
            return {"id": invoice_id, "status": inv["status"], "demo": True, "raw": inv}
        resp = requests.get(
            f"{SANDBOX_BASE}/v2/invoicing/invoices/{invoice_id}",
            headers={"Authorization": f"Bearer {self._get_token()}"},
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
        return {"id": invoice_id, "status": body.get("status"), "demo": False, "raw": body}

    # ------------------------------------------------- demo-only helpers ----
    def simulate_payment(self, invoice_id: str) -> dict:
        """Demo mode only: mark a simulated invoice as paid (for showcasing tracking)."""
        if not self.demo:
            raise RuntimeError("simulate_payment is only available in showcase (demo) mode")
        inv = self._demo_invoices.get(invoice_id)
        if not inv:
            raise ValueError(f"Unknown demo invoice {invoice_id}")
        inv = self._demo_invoices.get(invoice_id)
        if not inv:
            raise ValueError(f"Unknown demo invoice {invoice_id}")
        inv["status"] = "PAID"
        inv["paid_at"] = _now_iso()
        return {"id": invoice_id, "status": "PAID", "demo": True}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
