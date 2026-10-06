# Submission — PayPal AI Hackathon (Devpost)

## Title
**InvoicePilot — the AI agent that bills for you**

## Tagline
Chat in plain English; an AI agent drafts, creates, sends and tracks PayPal invoices — with a live trace of every step.

## Description

Freelancers lose hours — and real money — to invoicing admin: drafting invoices,
remembering due dates, and awkwardly chasing late payments. **InvoicePilot** is
an agentic-commerce copilot that removes all of it.

Talk to it like a colleague: *“Invoice Acme Corp $800 for the logo work, due
Friday.”* The agent parses your intent with an LLM, builds a draft, creates a
real invoice through the **PayPal Invoicing API (sandbox)**, sends it to your
client, generates the payment link, and keeps tracking payment status. Ask
*“What's the status of the Acme invoice?”* anytime. When a payment goes
overdue, say *“Remind Acme Corp”* and the agent AI-drafts a polite, professional
follow-up — shown for your review, never auto-sent.

Every turn is fully transparent: a **live agent-trace panel** shows each step —
intent parse → plan → draft → create → send → track — so you always see exactly
what the agent did and why. The invoice dashboard gives you statuses, payment
links and due dates at a glance.

InvoicePilot is built honest: without PayPal sandbox credentials it runs in a
clearly-labelled **showcase mode** with simulated responses (nothing is ever
presented as a real transaction), and without an LLM key it falls back to a
labelled rule-based parser. Add your free PayPal sandbox credentials and any
OpenAI-compatible LLM key, and it upgrades to the live stack with zero code
changes.

### Why agentic commerce
This isn't a form with a chatbot skin — it's an **agent that acts**: it takes a
natural-language goal and autonomously executes a multi-step commerce workflow
against PayPal's production APIs (draft → create → send → track), adapting its
plan to the intent, and explaining each action as it goes.

## Tracks / prize categories targeted
- Best Use of Agentic Commerce ($5,000)
- Best Use of PayPal + AI ($5,000)
- Most Impactful ($5,000)
- Best Demo Delivery ($5,000)
- Overall: 1st / 2nd / 3rd place

## Links (TBD at submit time)
- Demo video (YouTube, < 3 min): TBD
- Live demo URL: TBD
- GitHub repo: https://github.com/arindewangan/invoicepilot
- Static showcase (GitHub Pages): https://arindewangan.github.io/invoicepilot/demo/

## Built with
Python, Flask, PayPal REST Invoicing API v2 (sandbox), OpenAI-compatible LLM APIs,
vanilla JS + CSS, pytest

## License
MIT (LICENSE file in repo root)
