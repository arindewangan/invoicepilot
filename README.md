# InvoicePilot — AI Agentic Invoicing Copilot

> Built for the **PayPal AI Hackathon** (Devpost). Chat in plain English —
> the agent drafts, creates, sends and tracks **PayPal invoices**, with a live
> agent-trace of every step.

Say: *“Invoice Acme Corp $800 for the logo work, due Friday”* → InvoicePilot
parses the intent with an LLM, drafts the invoice, creates it via the **PayPal
Invoicing API (sandbox)**, sends it, generates the payment link, and keeps
tracking payment status. It can also AI-draft polite follow-up reminders for
overdue invoices (drafted only — never auto-sent).

## ✨ Features

- **Agentic chat** — natural-language invoicing, reminders, status checks
- **Live agent trace** — every step visible: parse intent → plan → draft → create → send → track
- **PayPal sandbox integration** — real Invoicing API v2 (OAuth2, create draft, send, status)
- **Showcase mode** — no credentials? The app runs with clearly-labelled simulated PayPal responses (nothing is ever faked as real)
- **LLM of your choice** — any OpenAI-compatible API for intent parsing + reminder copywriting; honest rule-based fallback without a key
- **Invoice dashboard** — statuses, payment links, one-click payment simulation (demo), live status refresh
- **Static showcase** — `demo/index.html` mirrors the app for GitHub Pages

## 🚀 Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

Run tests:

```bash
python -m pytest tests/ -q
```

## 🔑 Environment variables (all optional)

| Variable | Purpose | Default |
|---|---|---|
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | PayPal **sandbox** REST credentials | unset → showcase (simulated) mode |
| `LLM_API_KEY` | API key for an OpenAI-compatible LLM | unset → rule-based demo parsing |
| `LLM_BASE_URL` | LLM endpoint | `https://api.openai.com/v1` |
| `LLM_MODEL` | Model name | `gpt-4o-mini` |
| `PORT` | Server port | `5000` |

### Get free PayPal sandbox credentials (2 minutes)

1. Go to <https://developer.paypal.com> and log in (or create a free account).
2. Open **Apps & Credentials** → make sure **Sandbox** mode is selected.
3. Click **Create App** (or open the default app) — copy the **Client ID** and **Secret**.
4. Back in your terminal:
   ```bash
   export PAYPAL_CLIENT_ID="your-sandbox-client-id"
   export PAYPAL_CLIENT_SECRET="your-sandbox-secret"
   python app.py
   ```
   The header badge flips from *“Showcase (simulated)”* to *“Sandbox (live)”*.
   Sandbox invoices are test-only — no real money moves.

### Use a real LLM

```bash
export LLM_API_KEY="sk-..."            # any OpenAI-compatible key
# optional:
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
python app.py
```

Without a key, intent parsing and reminder drafting use transparent rule-based
fallbacks and the UI labels them as such.

## 🧠 How it works

```
user message
  → parse_intent (LLM JSON, or regex fallback)
  → plan (action → step sequence)
  → draft invoice
  → create via PayPal Invoicing API v2 (sandbox)  [or simulated in showcase mode]
  → send via PayPal
  → track status (live lookup)
  → reply + trace rendered in the UI
```

Reminders: the agent finds the overdue invoice, refreshes its status, and
AI-drafts a polite email — shown for review, **never auto-sent**.

## 📁 Project layout

```
invoicepilot/
├── app.py            # Flask app + API routes
├── agent.py          # agent pipeline with trace
├── paypal_client.py  # PayPal REST (sandbox) + showcase-mode simulation
├── llm.py            # OpenAI-compatible LLM client + fallbacks
├── store.py          # JSON invoice ledger
├── templates/        # UI
├── static/           # CSS / JS / logo
├── tests/            # pytest suite (PayPal + LLM mocked)
├── demo/index.html   # static clickable showcase (GitHub Pages)
└── assets/           # logo + banner
```

## 📄 License

MIT — see [LICENSE](LICENSE).
