const chat = document.getElementById('chat');
const traceBox = document.getElementById('trace');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const tableWrap = document.getElementById('tablewrap');

let PAYPAL_MODE = 'demo';

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
function md(s) { // tiny **bold** + link renderer
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/(https?:\/\/[^\s)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
    .replace(/\n/g, '<br>');
}

function addMsg(text, who) {
  const d = document.createElement('div');
  d.className = 'msg ' + who;
  d.innerHTML = md(text);
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}

function renderTrace(trace) {
  if (!trace || !trace.length) return;
  traceBox.innerHTML = '';
  for (const t of trace) {
    const d = document.createElement('div');
    d.className = 'tstep ' + (t.status || 'info');
    d.innerHTML = `<span class="tname">${esc(t.step)}</span>` +
      (t.ms != null ? `<span class="tms">${t.ms}ms</span>` : '') +
      `<div class="tdetail">${esc(t.detail)}</div>`;
    traceBox.appendChild(d);
  }
  traceBox.scrollTop = traceBox.scrollHeight;
}

function renderInvoices(rows) {
  if (!rows || !rows.length) {
    tableWrap.innerHTML = '<div class="empty">No invoices yet — ask the agent to invoice someone.</div>';
    return;
  }
  const body = rows.map(r => `
    <tr>
      <td class="mono">${esc(r.number || r.id)}</td>
      <td>${esc(r.recipient || '—')}</td>
      <td>${esc(r.description || '—')}</td>
      <td style="text-align:right"><b>${esc(r.currency || 'USD')} ${Number(r.amount || 0).toFixed(2)}</b></td>
      <td class="mono">${esc(r.due_date || '—')}</td>
      <td><span class="pill ${esc(r.status)}">${esc(r.status)}</span>${r.demo ? ' <span class="mono">demo</span>' : ''}</td>
      <td>
        ${r.payment_url ? `<button class="rowbtn" data-link="${esc(r.payment_url)}">Pay link</button>` : ''}
        ${PAYPAL_MODE === 'demo' && r.status !== 'PAID' ? `<button class="rowbtn" data-sim="${esc(r.id)}">Simulate payment</button>` : ''}
        <button class="rowbtn" data-status="${esc(r.id)}">Status</button>
      </td>
    </tr>`).join('');
  tableWrap.innerHTML = `<table><thead><tr>
    <th>Invoice</th><th>Client</th><th>For</th><th style="text-align:right">Amount</th>
    <th>Due</th><th>Status</th><th>Actions</th>
  </tr></thead><tbody>${body}</tbody></table>`;

  tableWrap.querySelectorAll('[data-link]').forEach(b =>
    b.onclick = () => window.open(b.dataset.link.replace(' (simulated)', ''), '_blank'));
  tableWrap.querySelectorAll('[data-sim]').forEach(b =>
    b.onclick = async () => {
      await fetch('/api/demo/simulate-payment/' + encodeURIComponent(b.dataset.sim), { method: 'POST' });
      loadInvoices();
    });
  tableWrap.querySelectorAll('[data-status]').forEach(b =>
    b.onclick = async () => {
      const r = await fetch('/api/invoice/' + encodeURIComponent(b.dataset.status)).then(x => x.json());
      addMsg(`Status check — **${esc(r.number || r.id)}** for ${esc(r.recipient)}: **${esc(r.status)}**`, 'bot');
      loadInvoices();
    });
}

async function loadInvoices() {
  const rows = await fetch('/api/invoices').then(r => r.json());
  renderInvoices(rows);
}

async function loadMode() {
  const m = await fetch('/api/mode').then(r => r.json());
  PAYPAL_MODE = m.paypal_mode;
  const llm = document.getElementById('badge-llm');
  llm.textContent = 'LLM: ' + m.llm_label;
  llm.classList.toggle('live', m.llm_configured);
  const pp = document.getElementById('badge-paypal');
  pp.textContent = 'PayPal: ' + (m.paypal_mode === 'demo' ? 'Showcase (simulated)' : 'Sandbox (live)');
  pp.classList.add(m.paypal_mode === 'demo' ? 'demo' : 'live');
  document.getElementById('mode-note').textContent = m.paypal_mode === 'demo'
    ? 'Showcase mode: PayPal calls are simulated — add PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET to use the live sandbox. Add LLM_API_KEY for full AI parsing.'
    : 'Live mode: talking to the real PayPal Sandbox API.';
  document.getElementById('btn-seed').style.display = m.paypal_mode === 'demo' ? '' : 'none';
  return m;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  sendBtn.disabled = true;
  addMsg(text, 'user');
  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.textContent = 'Agent is working…';
  chat.appendChild(typing);
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    }).then(r => r.json());
    typing.remove();
    addMsg(res.reply || '(no reply)', 'bot');
    renderTrace(res.trace);
    loadInvoices();
  } catch (e) {
    typing.remove();
    addMsg('Could not reach the server — is the app running?', 'bot');
  }
  sendBtn.disabled = false;
  input.focus();
}

const SUGGESTIONS = [
  'Invoice Acme Corp $800 for the logo work, due Friday',
  'Bill Globex Studio $1450 for the landing page, net 14',
  'List invoices',
  "What's the status of the Acme Corp invoice?",
  'Remind Acme Corp about their invoice',
];

function buildChips() {
  const box = document.getElementById('chips');
  box.innerHTML = '';
  for (const s of SUGGESTIONS) {
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = s;
    b.onclick = () => { input.value = s; send(); };
    box.appendChild(b);
  }
}

sendBtn.onclick = send;
input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
document.getElementById('btn-refresh').onclick = loadInvoices;
document.getElementById('btn-seed').onclick = async () => {
  await fetch('/api/demo/seed', { method: 'POST' });
  loadInvoices();
  addMsg('Loaded 3 demo invoices (one already paid) so you can explore tracking and reminders.', 'bot');
};

(async function init() {
  buildChips();
  await loadMode();
  await loadInvoices();
  addMsg("👋 I'm **InvoicePilot**, your AI invoicing copilot.\n\n" +
    "Tell me things like:\n“**Invoice Acme Corp $800 for the logo work, due Friday**”\n\n" +
    "I'll parse it, draft it, create it in **PayPal**, send it, and track payment — " +
    "watch every step in the **agent trace** →", 'bot');
})();
