"""InvoicePilot — AI agentic invoicing copilot (PayPal + AI).

Run:  pip install -r requirements.txt && python app.py
Then open http://localhost:5000
"""
import os
from datetime import date, timedelta

from flask import Flask, jsonify, render_template, request, send_from_directory

import agent
import store
from llm import llm_configured, llm_label
from paypal_client import PayPalClient

app = Flask(__name__)
paypal = PayPalClient()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/demo")
def demo():
    """Static clickable showcase (same file published to GitHub Pages)."""
    return send_from_directory(os.path.join(app.root_path, "demo"), "index.html")


@app.get("/api/mode")
def mode():
    return jsonify({
        "paypal_mode": paypal.mode,
        "paypal_label": paypal.mode_label(),
        "llm_configured": llm_configured(),
        "llm_label": llm_label(),
    })


@app.post("/api/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"reply": "Say something like: “Invoice Acme Corp $800 for the logo work, due Friday”.",
                        "trace": []})
    return jsonify(agent.run_agent(message, paypal, store))


@app.get("/api/invoices")
def invoices():
    return jsonify(store.list_invoices())


@app.get("/api/invoice/<invoice_id>")
def invoice_detail(invoice_id):
    rec = store.get_invoice_record(invoice_id)
    if not rec:
        return jsonify({"error": "not found"}), 404
    try:
        live = paypal.get_invoice(invoice_id)
        if live.get("status"):
            rec["status"] = live["status"]
            store.save_invoice(rec)
    except Exception:
        pass
    return jsonify(rec)


@app.post("/api/demo/seed")
def demo_seed():
    """Seed the ledger with sample invoices (showcase only)."""
    if not paypal.demo:
        return jsonify({"error": "seeding is only available in showcase (demo) mode"}), 400
    store.clear()
    samples = [
        ("Acme Corp", "billing@acme.example", 800.00, "Logo design work",
         (date.today() - timedelta(days=9)).isoformat()),
        ("Globex Studio", "accounts@globex.example", 1450.00, "Landing page build",
         (date.today() + timedelta(days=6)).isoformat()),
        ("Initech LLC", "ap@initech.example", 320.50, "Bug-fix retainer — September",
         (date.today() - timedelta(days=2)).isoformat()),
    ]
    created = []
    for recipient, email, amount, desc, due in samples:
        c = paypal.create_invoice({
            "recipient": recipient, "email": email, "amount": amount,
            "currency": "USD", "description": desc, "due_date": due,
        })
        s = paypal.send_invoice(c["id"])
        rec = {
            "id": c["id"], "number": c["raw"]["number"], "recipient": recipient,
            "email": email, "amount": amount, "currency": "USD", "description": desc,
            "due_date": due, "status": s["status"], "payment_url": s["payment_url"],
            "demo": True,
        }
        store.save_invoice(rec)
        created.append(rec)
    # mark one as paid to show the tracking range
    paypal.simulate_payment(created[0]["id"])
    created[0]["status"] = "PAID"
    store.save_invoice(created[0])
    return jsonify(created)


@app.post("/api/demo/simulate-payment/<invoice_id>")
def demo_simulate_payment(invoice_id):
    if not paypal.demo:
        return jsonify({"error": "only available in showcase (demo) mode"}), 400
    try:
        result = paypal.simulate_payment(invoice_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    rec = store.get_invoice_record(invoice_id)
    if rec:
        rec["status"] = "PAID"
        store.save_invoice(rec)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"InvoicePilot starting — PayPal: {paypal.mode_label()} | LLM: {llm_label()}")
    app.run(host="0.0.0.0", port=port, debug=False)
