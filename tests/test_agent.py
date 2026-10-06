"""End-to-end tests of the agent pipeline (PayPal demo mode, no network)."""
import agent
import store
from paypal_client import PayPalClient
from tests.conftest import _isolated_store


def _agent_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    st = _isolated_store(tmp_path, monkeypatch)
    return PayPalClient(), st


def _steps(result):
    return [t["step"] for t in result["trace"]]


def test_create_invoice_full_pipeline(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)
    res = agent.run_agent("Invoice Acme Corp $800 for the logo work, due Friday", paypal, st)

    steps = _steps(res)
    for expected in ("parse_intent", "plan", "draft", "create", "send", "track", "done"):
        assert expected in steps, f"missing trace step {expected}: {steps}"

    inv = res["invoice"]
    assert inv is not None
    assert inv["recipient"] == "Acme Corp"
    assert inv["amount"] == 800.0
    assert inv["status"] == "SENT"
    assert inv["demo"] is True
    assert "Acme Corp" in res["reply"]
    assert res["paypal_mode"] == "demo"
    assert res["parser"] == "rules"

    # persisted to the ledger
    rows = st.list_invoices()
    assert len(rows) == 1 and rows[0]["id"] == inv["id"]


def test_create_invoice_missing_details_asks(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)
    res = agent.run_agent("Invoice them", paypal, st)
    assert res["invoice"] is None
    assert "more" in res["reply"].lower() or "who" in res["reply"].lower()


def test_status_flow(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)
    created = agent.run_agent("Invoice Globex $200 for consulting", paypal, st)
    inv_id = created["invoice"]["id"]

    res = agent.run_agent(f"What's the status of invoice {inv_id}?", paypal, st)
    assert "SENT" in res["reply"]
    assert "fetch_status" in _steps(res)


def test_list_invoices(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)
    agent.run_agent("Invoice Acme $100 for a", paypal, st)
    agent.run_agent("Invoice Globex $200 for b", paypal, st)
    res = agent.run_agent("List invoices", paypal, st)
    assert res["invoices"] is not None and len(res["invoices"]) == 2
    assert "Acme" in res["reply"] and "Globex" in res["reply"]


def test_reminder_draft_uses_template_without_llm(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)
    agent.run_agent("Invoice Acme Corp $800 for logo work, due yesterday", paypal, st)
    res = agent.run_agent("Remind Acme Corp about their invoice", paypal, st)
    assert res["reminder"] is not None
    assert "Acme Corp" in res["reminder"]
    assert "did NOT send" in res["reply"]  # agent never auto-sends reminders
    assert "draft_reminder" in _steps(res)


def test_reminder_uses_llm_when_configured(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setattr(
        agent, "chat_complete",
        lambda system, user, json_mode=True, timeout=30: "Dear client, please pay. (LLM draft)",
    )
    agent.run_agent("Invoice Acme Corp $800 for logo work", paypal, st)
    res = agent.run_agent("Remind Acme Corp", paypal, st)
    assert res["reminder"] == "Dear client, please pay. (LLM draft)"


def test_help_action(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)
    res = agent.run_agent("hello", paypal, st)
    assert "InvoicePilot" in res["reply"]


def test_agent_never_crashes_on_paypal_error(monkeypatch, tmp_path):
    paypal, st = _agent_env(monkeypatch, tmp_path)

    def boom(draft):
        raise RuntimeError("PayPal is down")

    monkeypatch.setattr(paypal, "create_invoice", boom)
    res = agent.run_agent("Invoice Acme $100 for x", paypal, st)
    assert "error" in [t["status"] for t in res["trace"]]
    assert "went wrong" in res["reply"]
