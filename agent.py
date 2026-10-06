"""InvoicePilot agent: plain-English chat -> PayPal invoice actions.

Pipeline (every turn records an agent trace):
    1. parse_intent   — LLM (JSON) or rule-based fallback
    2. plan           — pick the action sequence for the intent
    3. execute        — draft -> create -> send -> track (PayPal sandbox or demo)
    4. reply          — natural-language summary + AI-drafted content where useful

Nothing here invents credentials: without PAYPAL_CLIENT_ID/SECRET the
PayPal client runs in labelled showcase mode; without LLM_API_KEY the
intent parser and copywriter fall back to labelled rule-based behaviour.
"""
import re
import time
from datetime import date, timedelta

from llm import chat_complete, llm_configured, llm_label

INTENT_SYSTEM = """You are the intent parser for InvoicePilot, an AI invoicing copilot.
Extract a JSON object from the user's message with these fields:
{
  "action": "create_invoice" | "send_reminder" | "check_status" | "list_invoices" | "help",
  "recipient": "client name or null",
  "email": "recipient email or null",
  "amount": number or null,
  "currency": "USD" (default) or 3-letter code,
  "description": "what the invoice is for or null",
  "due_text": "raw due-date phrase or null, e.g. 'Friday', 'tomorrow', 'net 14'",
  "invoice_ref": "invoice id/number the user refers to or null",
  "memo": "extra note or null"
}
Rules: 'invoice X $800 for Y due Friday' -> create_invoice. 'remind', 'nudge',
'follow up', 'overdue' -> send_reminder. 'status', 'paid yet', 'check' ->
check_status. 'show', 'list', 'all invoices' -> list_invoices. Greetings or
anything unclear -> help. Return ONLY the JSON object."""

REMINDER_SYSTEM = """You write polite, professional payment-reminder emails for freelancers.
Given invoice details, write a short friendly reminder email body (plain text,
no subject line, under 120 words). Warm tone, assume good intent, include the
amount, invoice number, due date and the payment link placeholder verbatim."""


# --------------------------------------------------------------------------
# trace helpers
# --------------------------------------------------------------------------
def new_trace():
    return []


def step(trace, name, status, detail, ms=None):
    trace.append({"step": name, "status": status, "detail": detail, "ms": ms})
    return trace


# --------------------------------------------------------------------------
# rule-based intent parsing (fallback when no LLM key)
# --------------------------------------------------------------------------
# Matches our invoice ids: DEMO-INV-<HEX8> in showcase mode, or PayPal's INV2-... ids.
INVOICE_REF_RE = re.compile(r"\b(DEMO-INV-[0-9A-Za-z]{4,}|INV[\w-]*\d[\w-]*)\b", re.I)
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def parse_due_date(text: str):
    """Parse a due-date phrase into an ISO date string, or None."""
    if not text:
        return None
    t = text.lower().strip()
    today = date.today()
    if "today" in t:
        return today.isoformat()
    if "tomorrow" in t:
        return (today + timedelta(days=1)).isoformat()
    m = re.search(r"in\s+(\d+)\s+days?", t)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"net\s*(\d+)", t)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat()
    if "next week" in t:
        return (today + timedelta(days=7)).isoformat()
    if "end of (the )?month" in t or "eom" in t:
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        return (nxt - timedelta(days=1)).isoformat()
    for name, wd in WEEKDAYS.items():
        if name in t:
            delta = (wd - today.weekday()) % 7 or 7
            if "next" in t:
                delta += 7
            return (today + timedelta(days=delta)).isoformat()
    return None


def rule_parse_intent(message: str) -> dict:
    msg = message.strip()
    low = msg.lower()
    intent = {
        "action": "help", "recipient": None, "email": None, "amount": None,
        "currency": "USD", "description": None, "due_text": None,
        "invoice_ref": None, "memo": None,
    }

    # reminder?
    if re.search(r"\b(remind|nudge|follow.?up|overdue|chase)\b", low):
        intent["action"] = "send_reminder"
        m = re.search(r"(?:remind|nudge|follow.?up(?: with)?|chase)\s+([\w\s.&'-]+?)(?:\s+about|\s*$)", msg, re.I)
        if m:
            intent["recipient"] = m.group(1).strip() or None
        ref = INVOICE_REF_RE.search(msg)
        if ref:
            intent["invoice_ref"] = ref.group(1).upper()
        return intent

    # status?
    if re.search(r"\b(status|paid yet|has .* paid|check on|tracking)\b", low):
        intent["action"] = "check_status"
        ref = INVOICE_REF_RE.search(msg)
        if ref:
            intent["invoice_ref"] = ref.group(1).upper()
        else:
            m = re.search(r"(?:status of|check on|has)\s+([\w\s.&'-]+)", msg, re.I)
            if m:
                intent["recipient"] = m.group(1).strip(" ?") or None
        return intent

    # list?
    if re.search(r"\b(list|show|all|my)\b.*\binvoices?\b", low) or re.search(r"\binvoices?\b.*\b(list|show)\b", low):
        intent["action"] = "list_invoices"
        return intent

    # create invoice?
    if re.search(r"\binvoic|\bbill\b|\bcharge\b", low):
        intent["action"] = "create_invoice"
        m = re.search(
            r"(?:invoice|bill|charge)\s+([\w\s.&'@-]+?)\s+\$?\s?([\d,]+(?:\.\d{1,2})?)"
            r"(?:\s*(usd|inr|eur|gbp))?\s*(?:for\s+(.+?))?\s*$",
            msg, re.I,
        )
        if m:
            recipient, amount, currency, rest = m.group(1), m.group(2), m.group(3), m.group(4)
            intent["recipient"] = recipient.strip(" ,")
            intent["amount"] = float(amount.replace(",", ""))
            if currency:
                intent["currency"] = currency.upper()
            if rest:
                # split "for <desc>" from "due <phrase>"
                dm = re.search(r"(.+?)(?:,?\s*due\s+(.+))?$", rest.strip(), re.I)
                if dm:
                    intent["description"] = dm.group(1).strip(" ,") or None
                    if dm.group(2):
                        intent["due_text"] = dm.group(2).strip()
        # email hiding in the message?
        em = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", msg)
        if em:
            intent["email"] = em.group(0)
            if intent["recipient"]:
                intent["recipient"] = intent["recipient"].replace(em.group(0), "").strip(" ,")
        return intent

    if re.search(r"\b(hi|hello|hey|help|what can you)\b", low):
        intent["action"] = "help"
    return intent


def parse_intent(message: str, trace) -> tuple:
    """Returns (intent dict, parser_used)."""
    t0 = time.perf_counter()
    if llm_configured():
        result = chat_complete(INTENT_SYSTEM, message, json_mode=True)
        if result and isinstance(result, dict) and result.get("action"):
            ms = int((time.perf_counter() - t0) * 1000)
            step(trace, "parse_intent", "ok",
                 f"LLM ({llm_label()}) extracted intent: {result.get('action')}", ms)
            return _normalise(result), "llm"
        step(trace, "parse_intent", "info",
             "LLM call failed — fell back to rule-based parser", int((time.perf_counter() - t0) * 1000))
    intent = rule_parse_intent(message)
    ms = int((time.perf_counter() - t0) * 1000)
    step(trace, "parse_intent", "ok",
         f"Rule-based parser extracted intent: {intent['action']} (no LLM key set)", ms)
    return intent, "rules"


def _normalise(intent: dict) -> dict:
    out = {
        "action": "help", "recipient": None, "email": None, "amount": None,
        "currency": "USD", "description": None, "due_text": None,
        "invoice_ref": None, "memo": None,
    }
    out.update({k: v for k, v in intent.items() if k in out})
    if out["amount"] is not None:
        try:
            out["amount"] = float(out["amount"])
        except (TypeError, ValueError):
            out["amount"] = None
    return out


# --------------------------------------------------------------------------
# reminder copywriting
# --------------------------------------------------------------------------
def draft_reminder(invoice: dict) -> tuple:
    """Returns (text, writer_used)."""
    if llm_configured():
        prompt = (
            f"Invoice {invoice.get('number') or invoice.get('id')} for "
            f"{invoice.get('recipient')} — {invoice.get('currency')} {invoice.get('amount'):.2f}, "
            f"due {invoice.get('due_date') or '—'}.\nPayment link: {invoice.get('payment_url') or '—'}"
        )
        text = chat_complete(REMINDER_SYSTEM, prompt, json_mode=False)
        if text:
            return text.strip(), "llm"
    # rule-based fallback, clearly a template
    return (
        f"Hi {invoice.get('recipient') or 'there'},\n\n"
        f"Just a friendly nudge — invoice {invoice.get('number') or invoice.get('id')} "
        f"for {invoice.get('currency', 'USD')} {float(invoice.get('amount') or 0):.2f} "
        f"was due on {invoice.get('due_date') or 'the date shown'}. If you've already "
        f"paid, please ignore this!\n\nYou can pay here: {invoice.get('payment_url') or '—'}\n\n"
        f"Thanks so much,\n— sent via InvoicePilot (template draft)",
        "template",
    )


# --------------------------------------------------------------------------
# main entry
# --------------------------------------------------------------------------
def run_agent(message: str, paypal, store) -> dict:
    trace = new_trace()
    t_start = time.perf_counter()

    intent, parser = parse_intent(message, trace)
    action = intent["action"]
    step(trace, "plan", "info", f"Plan: {action}" + _plan_detail(action, intent))

    try:
        if action == "create_invoice":
            result = _do_create(intent, paypal, store, trace)
        elif action == "send_reminder":
            result = _do_reminder(intent, paypal, store, trace)
        elif action == "check_status":
            result = _do_status(intent, paypal, store, trace)
        elif action == "list_invoices":
            result = _do_list(store, trace)
        else:
            result = _do_help(trace)
    except Exception as exc:  # never crash the chat on a provider error
        step(trace, "error", "error", f"{type(exc).__name__}: {exc}")
        result = {
            "reply": f"Something went wrong on my side: {exc}. Nothing was charged — "
                     "please try again or rephrase.",
            "invoice": None,
        }

    total_ms = int((time.perf_counter() - t_start) * 1000)
    step(trace, "done", "ok", f"Turn complete in {total_ms}ms", total_ms)
    return {
        "reply": result["reply"],
        "invoice": result.get("invoice"),
        "invoices": result.get("invoices"),
        "reminder": result.get("reminder"),
        "trace": trace,
        "parser": parser,
        "paypal_mode": paypal.mode,
    }


def _plan_detail(action, intent):
    if action == "create_invoice":
        return " → draft → create (PayPal) → send → track"
    if action == "send_reminder":
        return " → find overdue → draft reminder (AI) → preview"
    if action == "check_status":
        return " → look up invoice → fetch live status"
    if action == "list_invoices":
        return " → read local ledger"
    return ""


# ------------------------------------------------------------------ actions
def _do_create(intent, paypal, store, trace):
    missing = [f for f in ("recipient", "amount") if not intent.get(f)]
    if missing:
        step(trace, "validate", "error", f"Missing: {', '.join(missing)}")
        return {"reply": (
            "I need a bit more to create that invoice — who should I bill and for how much? "
            "Try: “Invoice Acme Corp $800 for the logo work, due Friday”.".
        ), "invoice": None}

    due = parse_due_date(intent.get("due_text"))
    draft = {
        "recipient": intent["recipient"],
        "email": intent.get("email"),
        "amount": intent["amount"],
        "currency": intent.get("currency", "USD"),
        "description": intent.get("description") or "Services rendered",
        "due_date": due,
        "memo": intent.get("memo"),
    }
    step(trace, "draft", "ok",
         f"Draft: {draft['recipient']} — {draft['currency']} {draft['amount']:.2f} "
         f"for “{draft['description']}”" + (f", due {due}" if due else ""))

    t0 = time.perf_counter()
    created = paypal.create_invoice(draft)
    step(trace, "create", "ok",
         f"PayPal {'(showcase)' if created.get('demo') else '(sandbox)'} created draft "
         f"{created['id']} — status {created['status']}",
         int((time.perf_counter() - t0) * 1000))

    t0 = time.perf_counter()
    sent = paypal.send_invoice(created["id"])
    step(trace, "send", "ok",
         f"Invoice sent — status {sent['status']}",
         int((time.perf_counter() - t0) * 1000))

    record = {
        "id": created["id"],
        "number": created.get("raw", {}).get("number") or created["id"],
        "recipient": draft["recipient"],
        "email": draft.get("email"),
        "amount": draft["amount"],
        "currency": draft["currency"],
        "description": draft["description"],
        "due_date": draft.get("due_date"),
        "status": sent["status"],
        "payment_url": sent.get("payment_url"),
        "demo": created.get("demo", False),
        "created_at": created.get("raw", {}).get("created"),
    }
    store.save_invoice(record)
    step(trace, "track", "ok",
         f"Tracking {record['id']} — current status: {record['status']}")

    sim_note = (" (showcase simulation — no real invoice was created)" if record["demo"] else "")
    reply = (
        f"Done! I created and sent a {record['currency']} {record['amount']:.2f} invoice "
        f"to {record['recipient']} for “{record['description']}”{(' due ' + due) if due else ''}.{sim_note}\n"
        f"Invoice {record['number']} is now {record['status']}. "
        f"Payment link: {record['payment_url']}\n"
        f"I'll keep tracking it — ask me for the status anytime, or say “remind {record['recipient']}” "
        f"if it goes overdue."
    )
    return {"reply": reply, "invoice": record}


def _find_invoice(intent, store):
    if intent.get("invoice_ref"):
        ref = intent["invoice_ref"].lower()
        for r in store.list_invoices():
            if ref in (r.get("id") or "").lower() or ref in (r.get("number") or "").lower():
                return r
    if intent.get("recipient"):
        name = intent["recipient"].lower()
        for r in store.list_invoices():
            if name in (r.get("recipient") or "").lower():
                return r
    return None


def _do_reminder(intent, paypal, store, trace):
    inv = _find_invoice(intent, store)
    if not inv:
        # fall back to the most overdue / oldest SENT invoice
        candidates = [r for r in store.list_invoices() if r.get("status") in ("SENT", "DRAFT")]
        inv = candidates[-1] if candidates else None
    if not inv:
        step(trace, "find_overdue", "error", "No invoices in the ledger yet")
        return {"reply": "I don't have any invoices to remind about yet — create one first!"}
    step(trace, "find_overdue", "ok",
         f"Selected {inv.get('number') or inv.get('id')} for {inv.get('recipient')} "
         f"({inv.get('currency')} {float(inv.get('amount') or 0):.2f}, {inv.get('status')})")

    # refresh status from PayPal when live
    try:
        live = paypal.get_invoice(inv["id"])
        inv["status"] = live.get("status") or inv["status"]
    except Exception:
        pass

    t0 = time.perf_counter()
    text, writer = draft_reminder(inv)
    step(trace, "draft_reminder", "ok",
         f"Reminder drafted with {'LLM (' + llm_label() + ')' if writer == 'llm' else 'template fallback'}",
         int((time.perf_counter() - t0) * 1000))

    reply = (
        f"Here's a polite reminder draft for {inv.get('recipient')} "
        f"(invoice {inv.get('number') or inv.get('id')}, currently {inv.get('status')}):\n\n{text}\n\n"
        f"⚠️ I drafted this but did NOT send it — review and send it yourself from your email."
    )
    return {"reply": reply, "invoice": inv, "reminder": text}


def _do_status(intent, paypal, store, trace):
    inv = _find_invoice(intent, store)
    if not inv:
        step(trace, "lookup", "error", "No matching invoice in the ledger")
        return {"reply": "I couldn't find that invoice. Say “list invoices” to see everything I'm tracking."}
    step(trace, "lookup", "ok", f"Found {inv.get('number') or inv.get('id')} for {inv.get('recipient')}")
    t0 = time.perf_counter()
    try:
        live = paypal.get_invoice(inv["id"])
        inv["status"] = live.get("status") or inv["status"]
        store.save_invoice(inv)
        src = "live from PayPal" if not live.get("demo") else "showcase ledger"
    except Exception as exc:
        src = f"ledger only (PayPal lookup failed: {exc})"
    step(trace, "fetch_status", "ok", f"Status: {inv['status']} ({src})",
         int((time.perf_counter() - t0) * 1000))
    return {"reply": (
        f"Invoice {inv.get('number') or inv.get('id')} for {inv.get('recipient')} — "
        f"{inv.get('currency')} {float(inv.get('amount') or 0):.2f} — is currently **{inv.get('status')}** "
        f"({src})." + (f" Payment link: {inv.get('payment_url')}" if inv.get("payment_url") else "")
    )}


def _do_list(store, trace):
    rows = store.list_invoices()
    step(trace, "read_ledger", "ok", f"{len(rows)} invoice(s) in the ledger")
    if not rows:
        return {"reply": "No invoices yet — tell me to invoice someone and I'll handle the rest!"}
    lines = [
        f"• {r.get('number') or r.get('id')} — {r.get('recipient')}: "
        f"{r.get('currency')} {float(r.get('amount') or 0):.2f} — {r.get('status')}"
        + (" (demo)" if r.get("demo") else "")
        for r in rows
    ]
    return {"reply": "Here's what I'm tracking:\n" + "\n".join(lines), "invoices": rows}


def _do_help(trace):
    step(trace, "help", "info", "Sent usage help")
    return {"reply": (
        "I'm InvoicePilot — your AI invoicing copilot. Talk to me like this:\n\n"
        "• “Invoice Acme Corp $800 for the logo work, due Friday” — I draft, create and send a PayPal invoice\n"
        "• “Remind Acme Corp about their invoice” — I AI-draft a polite follow-up\n"
        "• “What's the status of invoice DEMO-INV-…?” — I check PayPal live\n"
        "• “List invoices” — see everything I'm tracking\n\n"
        "Watch the agent trace on the right to see every step I take."
    )}
