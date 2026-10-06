"""Tests for the LLM client and the rule-based intent fallback."""
import os
from datetime import date, timedelta

import agent
import llm


def test_llm_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert llm.llm_configured() is False
    assert llm.chat_complete("sys", "hi") is None


def test_llm_label_demo_mode(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert "demo" in llm.llm_label().lower()


def test_rule_parse_create_invoice():
    i = agent.rule_parse_intent("Invoice Acme Corp $800 for the logo work, due Friday")
    assert i["action"] == "create_invoice"
    assert i["recipient"] == "Acme Corp"
    assert i["amount"] == 800.0
    assert i["description"] == "the logo work"
    assert i["due_text"] == "Friday"


def test_rule_parse_create_with_currency_and_email():
    i = agent.rule_parse_intent("Bill Globex Studio $1450 EUR for landing page, net 14, accounts@globex.example")
    assert i["action"] == "create_invoice"
    assert i["currency"] == "EUR"
    assert i["email"] == "accounts@globex.example"


def test_rule_parse_reminder():
    i = agent.rule_parse_intent("Remind Acme Corp about their invoice")
    assert i["action"] == "send_reminder"
    assert "Acme" in (i["recipient"] or "")


def test_rule_parse_status():
    i = agent.rule_parse_intent("What's the status of invoice DEMO-INV-ABC123?")
    assert i["action"] == "check_status"
    assert i["invoice_ref"] == "DEMO-INV-ABC123"


def test_rule_parse_list():
    assert agent.rule_parse_intent("List invoices")["action"] == "list_invoices"
    assert agent.rule_parse_intent("show me my invoices")["action"] == "list_invoices"


def test_rule_parse_help():
    assert agent.rule_parse_intent("hello")["action"] == "help"
    assert agent.rule_parse_intent("what can you do?")["action"] == "help"


def test_parse_due_date_weekday():
    got = agent.parse_due_date("Friday")
    assert got is not None
    d = date.fromisoformat(got)
    assert d.weekday() == 4  # Friday
    assert d > date.today()


def test_parse_due_date_relative():
    assert agent.parse_due_date("tomorrow") == (date.today() + timedelta(days=1)).isoformat()
    assert agent.parse_due_date("net 14") == (date.today() + timedelta(days=14)).isoformat()
    assert agent.parse_due_date("in 7 days") == (date.today() + timedelta(days=7)).isoformat()
    assert agent.parse_due_date("nonsense phrase") is None


def test_parse_intent_uses_llm_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setattr(
        agent, "chat_complete",
        lambda system, user, json_mode=True, timeout=30: {
            "action": "create_invoice", "recipient": "LLM Corp", "amount": 42,
            "currency": "USD", "description": "AI work", "due_text": None,
            "email": None, "invoice_ref": None, "memo": None,
        },
    )
    trace = agent.new_trace()
    intent, parser = agent.parse_intent("whatever the user said", trace)
    assert parser == "llm"
    assert intent["recipient"] == "LLM Corp"
    assert intent["amount"] == 42.0


def test_parse_intent_falls_back_when_llm_fails(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setattr(agent, "chat_complete", lambda *a, **k: None)
    trace = agent.new_trace()
    intent, parser = agent.parse_intent("Invoice Acme $100 for stuff", trace)
    assert parser == "rules"
    assert intent["action"] == "create_invoice"
