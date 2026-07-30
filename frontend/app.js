/* ==========================================================================
   RevAc Web Portal — app.js
   Council Admin / Sub-Consultant / Stakeholder dashboard (vanilla JS, no build step)
   ========================================================================== */

const state = { token: null, user: null, page: null };

const $ = s => document.querySelector(s);
const money = n => '₦' + Number(n || 0).toLocaleString('en-NG', { maximumFractionDigits: 0 });
const money2 = n => '₦' + Number(n || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dt = s => s ? new Date(String(s).replace(' ', 'T')).toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' }) : '—';
const d10 = s => s ? String(s).slice(0, 10) : '—';

function toast(m, bad) {
  const box = $('#toast');
  const d = document.createElement('div');
  d.className = 'toast' + (bad ? ' bad' : '');
  d.textContent = m;
  box.appendChild(d);
  setTimeout(() => d.remove(), 3800);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json',
      ...(state.token ? { Authorization: 'Bearer ' + state.token } : {}), ...(opts.headers || {}) }
  });
  if (r.status === 401) { doLogout(true); throw new Error('Session expired — sign in again'); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || 'Request failed');
  return d;
}

const qs = obj => Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== '')
  .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');

/* ---------------- persistence ---------------- */
const store = {
  save() { sessionStorage.setItem('revac_portal', JSON.stringify({ token: state.token, user: state.user })); },
  load() { try { return JSON.parse(sessionStorage.getItem('revac_portal') || 'null'); } catch { return null; } },
  clear() { sessionStorage.removeItem('revac_portal'); }
};

/* ---------------- auth ---------------- */
function quick(username) {
  $('#u').value = username;
  $('#p').value = 'revac2026';
  doLogin();
}

async function doLogin() {
  const errEl = $('#loginError');
  errEl.style.display = 'none';
  const username = $('#u').value.trim();
  const password = $('#p').value;
  if (!username || !password) { errEl.textContent = 'Enter a username and password'; errEl.style.display = 'block'; return; }
  try {
    const r = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    if (r.user.access_level === 'AGENT') {
      throw new Error('Field agent accounts use the mobile app at /m, not this portal');
    }
    state.token = r.token;
    state.user = r.user;
    store.save();
    boot();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

function doLogout(silent) {
  if (!silent) api('/api/auth/logout', { method: 'POST' }).catch(() => {});
  store.clear();
  state.token = null; state.user = null;
  $('#app').classList.remove('on');
  $('#login').style.display = '';
  $('#u').value = ''; $('#p').value = '';
}

/* ---------------- nav config ---------------- */
const NAV_SECTIONS = {
  COUNCIL_ADMIN: [
    { label: 'Overview', items: ['dashboard', 'global'] },
    { label: 'Revenue Operations', items: ['payers', 'bills', 'payments', 'receipts'] },
    { label: 'Finance', items: ['reconciliation', 'settlements', 'debt'] },
    { label: 'Administration', items: ['revenueItems', 'consultants', 'agents', 'terminals', 'audit'] },
  ],
  CONSULTANT: [
    { label: 'Overview', items: ['dashboard'] },
    { label: 'Revenue Operations', items: ['payers', 'bills', 'payments', 'receipts'] },
    { label: 'Finance', items: ['reconciliation', 'settlements', 'debt'] },
    { label: 'Team', items: ['agents', 'terminals'] },
  ],
  GLOBAL_VIEW: [
    { label: 'Overview', items: ['dashboard', 'global'] },
    { label: 'Administration', items: ['consultants'] },
  ],
};

const PAGE_META = {
  dashboard:      ['Revenue Dashboard', 'Real-time position across collections, bills and payers'],
  global:         ['Global Performance', 'Collections by sub-consultant and by ward'],
  payers:         ['Payer Registry', 'Enumerated ratepayers and businesses'],
  bills:          ['Assessment & e-Billing', 'Bills issued against the harmonised chart of revenue'],
  payments:       ['Payments', 'Confirmed collections across all e-channels'],
  receipts:       ['e-Receipts', 'Issued receipts and QR/SMS verification'],
  reconciliation: ['Reconciliation', 'Platform collections matched against the bank feed'],
  settlements:    ['Commission Settlements', 'Sub-consultant commission computation and status'],
  debt:           ['Debt Management', 'Overdue bills and the enforcement ladder'],
  revenueItems:   ['Revenue Items', 'The harmonised chart of revenue and its rates'],
  consultants:    ['Sub-Consultants', 'Portfolio holders onboarded to the platform'],
  agents:         ['Field Agents', 'Collection agents deployed to wards'],
  terminals:      ['POS Terminal Fleet', 'Deployed terminals and lifetime collections'],
  audit:          ['Audit Log', 'Immutable trail of sensitive actions'],
};

function renderNav() {
  const sections = NAV_SECTIONS[state.user.access_level] || NAV_SECTIONS.CONSULTANT;
  $('#nav').innerHTML = sections.map(sec => `
    <div class="nav-label">${esc(sec.label)}</div>
    ${sec.items.map(key => `<a data-page="${key}" onclick="go('${key}')">${esc(PAGE_META[key][0])}</a>`).join('')}
  `).join('');
}

/* ---------------- shell / boot ---------------- */
function boot() {
  $('#login').style.display = 'none';
  $('#app').classList.add('on');
  $('#avatar').textContent = (state.user.full_name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
  $('#whoName').textContent = state.user.full_name;
  $('#whoRole').textContent = state.user.consultant_name
    ? `${state.user.role_name} · ${state.user.consultant_name}` : state.user.role_name;
  renderNav();
  const sections = NAV_SECTIONS[state.user.access_level] || NAV_SECTIONS.CONSULTANT;
  go(sections[0].items[0]);
}

function go(page) {
  state.page = page;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.page === page));
  const [title, sub] = PAGE_META[page] || ['—', ''];
  $('#pageTitle').textContent = title;
  $('#pageSub').textContent = sub;
  loadPage(page);
  toggleSidebar(false);
}

function toggleSidebar(force) {
  const open = force !== undefined ? force : !document.querySelector('.sidebar').classList.contains('open');
  document.querySelector('.sidebar').classList.toggle('open', open);
  $('#sidebarBackdrop').classList.toggle('on', open);
}

function loadPage(page) {
  const renderers = {
    dashboard: renderDashboard, global: renderGlobal, payers: renderPayers, bills: renderBills,
    payments: renderPayments, receipts: renderReceipts, reconciliation: renderReconciliation,
    settlements: renderSettlements, debt: renderDebt, revenueItems: renderRevenueItems,
    consultants: renderConsultants, agents: renderAgents, terminals: renderTerminals, audit: renderAudit,
  };
  (renderers[page || state.page] || renderDashboard)();
}

function setPage(html) { $('#pages').innerHTML = `<div class="page">${html}</div>`; }

/* ---------------- modal ---------------- */
function openModal(title, body, foot) {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = body;
  $('#modalFoot').innerHTML = foot || '';
  $('#modalBg').classList.add('on');
}
function closeModal() { $('#modalBg').classList.remove('on'); }

/* ---------------- document viewer (Demand Notice / Demand Bill) ---------------- */
function openDoc(title, url) {
  $('#docViewerTitle').textContent = title;
  $('#docViewerFrame').src = url;
  $('#docViewerBg').classList.add('on');
}
function closeDocViewer() {
  $('#docViewerBg').classList.remove('on');
  $('#docViewerFrame').src = 'about:blank';
}
function printDocViewer() {
  const win = $('#docViewerFrame').contentWindow;
  if (win) win.print();
}
function openDemandNotice(billRef) {
  openDoc('Harmonised Demand Notice', '/frontend/demand-notice.html?bill=' + encodeURIComponent(billRef));
}
function openDemandBill(billRef) {
  openDoc('Harmonised Demand Bill', '/frontend/demand-bill.html?bill=' + encodeURIComponent(billRef));
}

/* ---------------- dashboard ---------------- */
const CHANNEL_COLORS = { POS: '#13543F', OTC: '#C08B2C', IB_MB: '#1C6B51', USSD: '#9A6B00', FIRSTMONIE: '#52635C' };

async function renderDashboard() {
  setPage('<div class="empty">Loading dashboard…</div>');
  let d;
  try { d = await api('/api/dashboard/summary'); } catch (e) { setPage(`<div class="notice bad">${esc(e.message)}</div>`); return; }

  const channelTotal = d.by_channel.reduce((s, c) => s + c.amount, 0) || 1;
  const flow = d.by_channel.filter(c => c.amount > 0).map(c =>
    `<div style="flex-grow:${c.amount};background:${CHANNEL_COLORS[c.channel_code] || '#888'}">${Math.round(c.amount / channelTotal * 100)}%</div>`
  ).join('');
  const legend = d.by_channel.map(c => `<span><span class="dot" style="background:${CHANNEL_COLORS[c.channel_code] || '#888'}"></span>${esc(c.channel_name)} · ${money(c.amount)}</span>`).join('');

  const maxItem = Math.max(...d.by_item.map(i => i.billed), 1);
  const itemBars = d.by_item.map(i => `
    <div class="bar-row"><div class="nm">${esc(i.item_name)}</div>
      <div class="track"><div class="fill" style="width:${(i.billed / maxItem * 100).toFixed(1)}%"></div></div>
      <div class="amt num">${money(i.billed)}</div></div>`).join('');

  const maxTrend = Math.max(...d.trend.map(t => t.amount || 0), 1);
  const trendBars = d.trend.map(t =>
    `<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:78px">
      <div title="${d10(t.d)}: ${money(t.amount)}" style="background:var(--green-600);border-radius:2px 2px 0 0;height:${Math.max((t.amount || 0) / maxTrend * 100, 2)}%"></div>
    </div>`).join('');

  setPage(`
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card stat"><div class="label">Total Billed</div><div class="value">${money(d.billed)}</div><div class="delta">${d.bills} bills issued</div></div>
      <div class="card stat accent"><div class="label">Total Collected</div><div class="value">${money(d.collected)}</div><div class="delta">${d.billed ? Math.round(d.collected / d.billed * 100) : 0}% of billed</div></div>
      <div class="card stat"><div class="label">Outstanding</div><div class="value">${money(d.outstanding)}</div><div class="delta">${d.assessments} assessments</div></div>
      <div class="card stat"><div class="label">Registered Payers</div><div class="value">${d.payers.toLocaleString()}</div><div class="delta">${d.active_agents} active field agents</div></div>
    </div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card">
        <h3>Collections by e-Channel</h3>
        <div class="flowstrip">${flow || '<div style="background:#EEF2F0;color:var(--ink-40)">No confirmed payments yet</div>'}</div>
        <div class="flowlegend">${legend}</div>
      </div>
      <div class="card">
        <h3>Collections — last 14 days</h3>
        <div style="display:flex;align-items:flex-end;gap:3px;height:78px">${trendBars}</div>
      </div>
    </div>
    <div class="card">
      <h3>Top Revenue Items by Amount Billed</h3>
      ${itemBars || '<div class="empty">No billing activity yet</div>'}
    </div>
  `);
}

/* ---------------- global performance ---------------- */
async function renderGlobal() {
  setPage('<div class="empty">Loading global performance…</div>');
  let d;
  try { d = await api('/api/dashboard/global'); } catch (e) { setPage(`<div class="notice bad">${esc(e.message)}</div>`); return; }

  const consultRows = d.consultants.map(c => `
    <tr><td>${esc(c.consultant_name)}</td><td class="r num">${money(c.billed)}</td>
      <td class="r num">${money(c.collected)}</td><td class="r num">${c.collection_rate}%</td>
      <td class="r num">${money(c.commission_accrued)}</td>
      <td><span class="tag ${c.status === 'ACTIVE' ? 'ok' : c.status === 'SUSPENDED' ? 'bad' : 'neutral'}">${esc(c.status)}</span></td></tr>`).join('');

  const wardRows = d.wards.map(w => `
    <tr><td>${esc(w.ward_name)}</td><td class="r">${w.payers}</td><td class="r num">${money(w.collected)}</td></tr>`).join('');

  setPage(`
    <div class="card" style="margin-bottom:16px">
      <h3>Sub-Consultant Performance</h3>
      <div class="table-wrap"><table><thead><tr><th>Consultant</th><th class="r">Billed</th>
        <th class="r">Collected</th><th class="r">Collection Rate</th><th class="r">Commission Accrued</th><th>Status</th></tr></thead>
        <tbody>${consultRows || '<tr><td colspan="6" class="empty">No consultants</td></tr>'}</tbody></table></div>
    </div>
    <div class="card">
      <h3>Collections by Ward</h3>
      <div class="table-wrap"><table><thead><tr><th>Ward</th><th class="r">Payers</th><th class="r">Collected</th></tr></thead>
        <tbody>${wardRows || '<tr><td colspan="3" class="empty">No ward data</td></tr>'}</tbody></table></div>
    </div>
  `);
}

/* ---------------- payers ---------------- */
async function renderPayers(q) {
  setPage(`
    <div class="toolbar">
      <input class="grow" id="payerSearch" placeholder="Search by name, payer ref or phone…" value="${esc(q || '')}">
      <button class="btn-ghost" onclick="renderPayers($('#payerSearch').value)">Search</button>
      <button class="btn-ghost" onclick="openPayerForm('INDIVIDUAL')">Register Individual</button>
      <button class="btn-primary" onclick="openPayerForm('BUSINESS')">Register Business</button>
    </div>
    <div class="card"><div class="table-wrap" id="payerTable"><div class="empty">Loading…</div></div></div>
  `);
  $('#payerSearch').addEventListener('keydown', e => { if (e.key === 'Enter') renderPayers(e.target.value); });
  let rows;
  try { rows = await api('/api/payers?' + qs({ q })); } catch (e) { $('#payerTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#payerTable').innerHTML = `
    <table><thead><tr><th>Payer Ref</th><th>Name</th><th>Type</th><th>Ward</th><th>Phone</th><th>KYC</th></tr></thead>
    <tbody>${rows.map(p => `
      <tr style="cursor:pointer" onclick="openPayerDetail(${p.payer_id})">
        <td class="num">${esc(p.payer_ref)}</td><td>${esc(p.full_name)}</td><td>${esc(p.payer_type)}</td>
        <td>${esc(p.ward_name || '—')}</td><td class="num">${esc(p.phone || '—')}</td>
        <td><span class="tag ${p.kyc_status === 'VERIFIED' ? 'ok' : p.kyc_status === 'FLAGGED' ? 'bad' : 'warn'}">${esc(p.kyc_status)}</span></td>
      </tr>`).join('') || '<tr><td colspan="6" class="empty">No payers match</td></tr>'}</tbody></table>`;
}

async function openPayerDetail(id) {
  openModal('Payer', '<div class="empty">Loading…</div>');
  let p, drafts;
  try {
    [p, drafts] = await Promise.all([api('/api/payers/' + id), api(`/api/payers/${id}/draft-assessments`)]);
  } catch (e) { $('#modalBody').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#modalTitle').textContent = p.full_name;
  $('#modalBody').innerHTML = `
    <div class="kv"><span>Payer ref</span><b class="num">${esc(p.payer_ref)}</b></div>
    <div class="kv"><span>Type</span><b>${esc(p.payer_type)}</b></div>
    <div class="kv"><span>Ward</span><b>${esc(p.ward_name || '—')}</b></div>
    <div class="kv"><span>Phone</span><b class="num">${esc(p.phone || '—')}</b></div>
    <div class="kv"><span>KYC status</span><b>${esc(p.kyc_status)}</b></div>
    <h3 style="margin:18px 0 8px">Assets (${p.assets.length})</h3>
    ${p.assets.map(a => `<div class="kv"><span>${esc(a.asset_ref)} · ${esc(a.asset_type)}</span><b>${esc(a.description || '')}</b></div>`).join('') || '<div class="empty">No enumerated assets</div>'}
    <h3 style="margin:18px 0 8px">Enumerated Revenue Items — not yet billed (${drafts.length})</h3>
    ${drafts.length ? `
      ${drafts.map(a => `<div class="kv"><span>${esc(a.harmonised_code)} — ${esc(a.item_name)}</span><b class="num">${money(a.assessed_amount)}</b></div>`).join('')}
      <div class="kv"><span><b>Total if billed now</b></span><b class="num">${money(drafts.reduce((s, a) => s + a.assessed_amount, 0))}</b></div>
      <button class="btn-brass btn-sm" style="margin-top:8px" onclick="issueHarmonizedBill(${p.payer_id})">Issue Harmonized Bill</button>
    ` : '<div class="empty">Nothing pending — enumerate revenue items for this payer to build one up</div>'}
    <h3 style="margin:18px 0 8px">Bills (${p.bills.length})</h3>
    ${p.bills.map(b => `<div class="kv"><span>${esc(b.bill_ref)} · due ${d10(b.due_date)}</span><b class="num">${money(b.balance)} of ${money(b.total_amount)}
      <a href="javascript:void(0)" onclick="openDemandNotice('${esc(b.bill_ref)}')" style="margin-left:8px;font-weight:400">notice</a>
      <a href="javascript:void(0)" onclick="openDemandBill('${esc(b.bill_ref)}')" style="margin-left:6px;font-weight:400">bill</a></b></div>`).join('') || '<div class="empty">No bills</div>'}
  `;
  $('#modalFoot').innerHTML = `<button class="btn-ghost" onclick="closeModal()">Close</button>`;
}

async function issueHarmonizedBill(payerId) {
  try {
    const r = await api('/api/bills', { method: 'POST', body: JSON.stringify({ payer_id: payerId, bill_all_drafts: true }) });
    toast(`Harmonized bill issued — ${r.bill_ref} (${money(r.total_amount)})`);
    openPayerDetail(payerId);
    if (state.page === 'bills') renderBills();
  } catch (e) { toast(e.message, true); }
}

async function openPayerForm(payerType) {
  let wards = [], items = [];
  try { [wards, items] = await Promise.all([api('/api/wards'), api('/api/revenue-items')]); } catch {}
  const isIndividual = payerType === 'INDIVIDUAL';
  const itemChecks = items.filter(i => i.current_rate != null).map(i => `
    <label style="display:flex;align-items:center;gap:8px;font-weight:400;margin-bottom:6px">
      <input type="checkbox" class="pf-item" value="${i.revenue_item_id}" style="width:auto">
      ${esc(i.harmonised_code)} — ${esc(i.item_name)} (${money(i.current_rate)})
    </label>`).join('');

  openModal(isIndividual ? 'Register Individual' : 'Register Business', `
    <input type="hidden" id="pf_type" value="${payerType}">
    <div class="row"><div class="field"><label>${isIndividual ? 'Full name' : 'Business name'}</label><input id="pf_name"></div>
      <div class="field"><label>Phone</label><input id="pf_phone"></div></div>
    <div class="row">
      <div class="field"><label>${isIndividual ? 'NIN / BVN' : 'TIN'}</label><input id="pf_idnum" placeholder="${isIndividual ? 'National Identity / Bank Verification Number' : 'Tax Identification Number'}"></div>
      <div class="field"><label>Email</label><input id="pf_email"></div>
    </div>
    <div class="row"><div class="field"><label>Ward</label><select id="pf_ward"><option value="">—</option>${wards.map(w => `<option value="${w.ward_id}">${esc(w.ward_name)}</option>`).join('')}</select></div>
      <div class="field"><label>Address</label><input id="pf_addr"></div></div>
    <div class="field"><label>Revenue items liable (optional — enumerate what applies now)</label>
      <div style="max-height:180px;overflow-y:auto;border:1px solid var(--line);border-radius:8px;padding:10px">${itemChecks}</div>
    </div>
    <div id="pf_err"></div>
  `, `<button class="btn-ghost" onclick="closeModal()">Cancel</button><button class="btn-primary" onclick="submitPayerForm()">Register</button>`);
}

async function submitPayerForm(force) {
  const payerType = $('#pf_type').value;
  const isIndividual = payerType === 'INDIVIDUAL';
  const idnum = $('#pf_idnum').value.trim();
  const revenue_item_ids = [...document.querySelectorAll('.pf-item:checked')].map(el => Number(el.value));
  const body = {
    full_name: $('#pf_name').value.trim(), payer_type: payerType,
    phone: $('#pf_phone').value.trim(), email: $('#pf_email').value.trim(),
    ward_id: $('#pf_ward').value || null, address: $('#pf_addr').value.trim(),
    revenue_item_ids, force: !!force,
    ...(isIndividual ? { nin_bvn: idnum } : { tin: idnum }),
  };
  if (!body.full_name) { $('#pf_err').innerHTML = '<div class="notice bad">Enter the payer\'s name</div>'; return; }
  try {
    const r = await api('/api/payers', { method: 'POST', body: JSON.stringify(body) });
    closeModal();
    toast(`${isIndividual ? 'Individual' : 'Business'} registered — ${r.payer_ref}${r.draft_assessments_created ? ` (${r.draft_assessments_created} item(s) enumerated)` : ''}`);
    renderPayers();
  } catch (e) {
    $('#pf_err').innerHTML = `<div class="notice bad">${esc(e.message)}
      ${/already exists/.test(e.message) ? '<div style="margin-top:8px"><button class="btn-brass btn-sm" onclick="submitPayerForm(true)">Register anyway</button></div>' : ''}</div>`;
  }
}

/* ---------------- bills ---------------- */
async function renderBills(status) {
  status = status || '';
  setPage(`
    <div class="toolbar">
      <select id="billStatus" class="grow" style="max-width:220px" onchange="renderBills(this.value)">
        <option value="">All statuses</option>
        ${['ISSUED', 'PART_PAID', 'PAID', 'OVERDUE', 'CANCELLED'].map(s => `<option value="${s}" ${s === status ? 'selected' : ''}>${s.replace('_', ' ')}</option>`).join('')}
      </select>
      <div class="grow"></div>
      <button class="btn-primary" onclick="openBillForm()">New Bill</button>
    </div>
    <div class="card"><div class="table-wrap" id="billTable"><div class="empty">Loading…</div></div></div>
  `);
  let rows;
  try { rows = await api('/api/bills?' + qs({ status })); } catch (e) { $('#billTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  const tagOf = s => s === 'PAID' ? 'ok' : s === 'OVERDUE' ? 'bad' : s === 'PART_PAID' ? 'warn' : s === 'CANCELLED' ? 'neutral' : 'brass';
  $('#billTable').innerHTML = `
    <table><thead><tr><th>Bill Ref</th><th>Payer</th><th>Consultant</th><th class="r">Total</th><th class="r">Balance</th><th>Due</th><th>Status</th><th></th></tr></thead>
    <tbody>${rows.map(b => `
      <tr><td class="num">${esc(b.bill_ref)}</td><td>${esc(b.full_name)}</td><td>${esc(b.consultant_name || '—')}</td>
        <td class="r num">${money(b.total_amount)}</td><td class="r num">${money(b.balance)}</td>
        <td class="num">${d10(b.due_date)}</td><td><span class="tag ${tagOf(b.status)}">${esc(b.status.replace('_', ' '))}</span></td>
        <td style="white-space:nowrap">
          <button class="btn-ghost btn-sm" onclick="openDemandNotice('${esc(b.bill_ref)}')">Notice</button>
          <button class="btn-ghost btn-sm" onclick="openDemandBill('${esc(b.bill_ref)}')">Bill</button>
        </td></tr>`).join('') || '<tr><td colspan="8" class="empty">No bills match</td></tr>'}</tbody></table>`;
}

let billLines = [];

async function openBillForm() {
  billLines = [];
  let items = [];
  try { items = await api('/api/revenue-items'); } catch {}
  window.__revenueItems = items.filter(i => i.current_rate != null);
  openModal('New Bill', `
    <div class="field"><label>Payer ref or phone</label><input id="bf_payer" placeholder="Search then press Enter"></div>
    <div id="bf_payer_found"></div>
    <div class="row">
      <div class="field"><label>Revenue item</label><select id="bf_item">${window.__revenueItems.map(i => `<option value="${i.revenue_item_id}">${esc(i.harmonised_code)} — ${esc(i.item_name)} (${money(i.current_rate)})</option>`).join('')}</select></div>
      <div class="field" style="max-width:110px"><label>Qty</label><input id="bf_qty" type="number" value="1" min="1"></div>
      <div class="field" style="max-width:120px"><label>&nbsp;</label><button class="btn-ghost" style="width:100%" onclick="addBillLine()">Add line</button></div>
    </div>
    <div id="bf_lines"></div>
    <div id="bf_err"></div>
  `, `<button class="btn-ghost" onclick="closeModal()">Cancel</button><button class="btn-primary" onclick="submitBillForm()">Issue Bill</button>`);
  $('#bf_payer').addEventListener('keydown', async e => {
    if (e.key !== 'Enter') return;
    const q = e.target.value.trim();
    if (!q) return;
    const found = await api('/api/payers?' + qs({ q }));
    window.__billPayer = found[0] || null;
    $('#bf_payer_found').innerHTML = found[0]
      ? `<div class="notice info">${esc(found[0].full_name)} · ${esc(found[0].payer_ref)}</div>`
      : `<div class="notice bad">No payer found for "${esc(q)}"</div>`;
  });
}

function addBillLine() {
  const itemId = $('#bf_item').value;
  const qty = Number($('#bf_qty').value) || 1;
  const item = window.__revenueItems.find(i => String(i.revenue_item_id) === itemId);
  if (!item) return;
  billLines.push({ revenue_item_id: item.revenue_item_id, quantity: qty, label: item.item_name, amount: item.current_rate * qty });
  renderBillLines();
}
function removeBillLine(i) { billLines.splice(i, 1); renderBillLines(); }
function renderBillLines() {
  const total = billLines.reduce((s, l) => s + l.amount, 0);
  $('#bf_lines').innerHTML = billLines.length ? `
    ${billLines.map((l, i) => `<div class="kv"><span>${esc(l.label)} × ${l.quantity}</span><b class="num">${money(l.amount)} <a href="javascript:void(0)" onclick="removeBillLine(${i})" style="color:var(--danger);margin-left:8px">remove</a></b></div>`).join('')}
    <div class="kv"><span><b>Total</b></span><b class="num">${money(total)}</b></div>` : '<div class="empty">No lines added yet</div>';
}

async function submitBillForm() {
  if (!window.__billPayer) { $('#bf_err').innerHTML = '<div class="notice bad">Search and select a payer first</div>'; return; }
  if (!billLines.length) { $('#bf_err').innerHTML = '<div class="notice bad">Add at least one revenue item</div>'; return; }
  try {
    const r = await api('/api/bills', {
      method: 'POST',
      body: JSON.stringify({ payer_id: window.__billPayer.payer_id, lines: billLines.map(l => ({ revenue_item_id: l.revenue_item_id, quantity: l.quantity })) }),
    });
    closeModal();
    toast(`Bill issued — ${r.bill_ref} (${money(r.total_amount)})`);
    renderBills();
  } catch (e) { $('#bf_err').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
}

/* ---------------- payments ---------------- */
async function renderPayments() {
  setPage('<div class="card"><div class="table-wrap" id="payTable"><div class="empty">Loading…</div></div></div>');
  let rows;
  try { rows = await api('/api/payments'); } catch (e) { $('#payTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#payTable').innerHTML = `
    <table><thead><tr><th>Payment Ref</th><th>Bill</th><th>Payer</th><th>Channel</th><th class="r">Amount</th><th>Status</th><th>Paid At</th></tr></thead>
    <tbody>${rows.map(p => `
      <tr><td class="num">${esc(p.payment_ref)}</td><td class="num">${esc(p.bill_ref)}</td><td>${esc(p.full_name)}</td>
        <td>${esc(p.channel_name)}</td><td class="r num">${money2(p.amount)}</td>
        <td><span class="tag ${p.txn_status === 'CONFIRMED' ? 'ok' : p.txn_status === 'FAILED' ? 'bad' : 'warn'}">${esc(p.txn_status)}</span></td>
        <td class="num">${dt(p.paid_at)}</td></tr>`).join('') || '<tr><td colspan="7" class="empty">No payments recorded yet</td></tr>'}</tbody></table>`;
}

/* ---------------- receipts ---------------- */
async function renderReceipts() {
  setPage('<div class="card"><div class="table-wrap" id="rcptTable"><div class="empty">Loading…</div></div></div>');
  let rows;
  try { rows = await api('/api/receipts'); } catch (e) { $('#rcptTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#rcptTable').innerHTML = `
    <table><thead><tr><th>Receipt Ref</th><th>Bill</th><th>Payer</th><th>Channel</th><th class="r">Amount</th><th>Issued</th><th>Verified</th><th></th></tr></thead>
    <tbody>${rows.map(r => `
      <tr><td class="num">${esc(r.receipt_ref)}</td><td class="num">${esc(r.bill_ref)}</td><td>${esc(r.full_name)}</td>
        <td>${esc(r.channel_name)}</td><td class="r num">${money2(r.amount)}</td><td class="num">${dt(r.issued_at)}</td>
        <td class="r">${r.verified_count}</td>
        <td><button class="btn-ghost btn-sm" onclick="verifyReceipt('${r.qr_token}')">Verify</button></td></tr>`).join('') || '<tr><td colspan="8" class="empty">No receipts issued yet</td></tr>'}</tbody></table>`;
}

async function verifyReceipt(token) {
  try {
    const r = await api('/api/verify/' + token);
    toast(`Valid — ${r.receipt.receipt_ref} · ${money2(r.receipt.amount)} · ${r.receipt.full_name}`);
    renderReceipts();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- reconciliation ---------------- */
async function renderReconciliation() {
  const today = new Date().toISOString().slice(0, 10);
  setPage(`
    <div class="toolbar">
      <input id="reconDate" type="date" value="${today}" style="max-width:180px">
      <button class="btn-primary" onclick="runReconciliation()">Run Reconciliation</button>
    </div>
    <div class="card" style="margin-bottom:16px"><h3>Recent Runs</h3><div class="table-wrap" id="reconRuns"><div class="empty">Loading…</div></div></div>
    <div class="card"><h3>Unmatched Bank Credits</h3><div class="table-wrap" id="reconUnmatched"></div></div>
  `);
  await loadReconciliation();
}

async function loadReconciliation() {
  let d;
  try { d = await api('/api/reconciliation'); } catch (e) { $('#reconRuns').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#reconRuns').innerHTML = `
    <table><thead><tr><th>Date</th><th>Channel</th><th class="r">Platform</th><th class="r">Bank</th><th class="r">Variance</th><th>Status</th></tr></thead>
    <tbody>${d.runs.map(r => `
      <tr><td class="num">${d10(r.run_date)}</td><td>${esc(r.channel_name || '—')}</td>
        <td class="r num">${money(r.total_platform)}</td><td class="r num">${money(r.total_bank)}</td>
        <td class="r num">${money(r.variance)}</td><td><span class="tag ${r.status === 'BALANCED' ? 'ok' : r.status === 'CLOSED' ? 'neutral' : 'bad'}">${esc(r.status)}</span></td></tr>`).join('') || '<tr><td colspan="6" class="empty">No reconciliation runs yet</td></tr>'}</tbody></table>`;
  $('#reconUnmatched').innerHTML = `
    <table><thead><tr><th>Bank Ref</th><th>Channel</th><th>Narration</th><th class="r">Amount</th><th>Value Date</th><th>Status</th></tr></thead>
    <tbody>${d.unmatched.map(f => `
      <tr><td class="num">${esc(f.bank_txn_ref)}</td><td>${esc(f.channel_name)}</td><td>${esc(f.narration || '—')}</td>
        <td class="r num">${money(f.amount)}</td><td class="num">${d10(f.value_date)}</td>
        <td><span class="tag bad">${esc(f.match_status)}</span></td></tr>`).join('') || '<tr><td colspan="6" class="empty">Nothing unmatched — all clean</td></tr>'}</tbody></table>`;
}

async function runReconciliation() {
  try {
    const r = await api('/api/reconciliation/run', { method: 'POST', body: JSON.stringify({ date: $('#reconDate').value }) });
    toast(`Reconciliation run for ${r.run_date} complete`);
    loadReconciliation();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- settlements ---------------- */
async function renderSettlements() {
  const isAdmin = state.user.access_level === 'COUNCIL_ADMIN';
  const start = new Date(); start.setDate(1);
  setPage(`
    ${isAdmin ? `
    <div class="toolbar">
      <input id="setStart" type="date" value="${start.toISOString().slice(0, 10)}" style="max-width:180px">
      <input id="setEnd" type="date" value="${new Date().toISOString().slice(0, 10)}" style="max-width:180px">
      <button class="btn-primary" onclick="computeSettlements()">Compute Settlements</button>
    </div>` : ''}
    <div class="card"><div class="table-wrap" id="setTable"><div class="empty">Loading…</div></div></div>
  `);
  await loadSettlements();
}

async function loadSettlements() {
  let rows;
  try { rows = await api('/api/settlements'); } catch (e) { $('#setTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#setTable').innerHTML = `
    <table><thead><tr><th>Consultant</th><th>Period</th><th class="r">Gross Collections</th><th class="r">Rate</th><th class="r">Commission</th><th>Status</th></tr></thead>
    <tbody>${rows.map(s => `
      <tr><td>${esc(s.consultant_name)}</td><td class="num">${d10(s.period_start)} – ${d10(s.period_end)}</td>
        <td class="r num">${money(s.gross_collections)}</td><td class="r num">${s.commission_rate}%</td>
        <td class="r num">${money(s.commission_amount)}</td>
        <td><span class="tag ${s.status === 'SETTLED' ? 'ok' : s.status === 'DISPUTED' ? 'bad' : 'brass'}">${esc(s.status)}</span></td></tr>`).join('') || '<tr><td colspan="6" class="empty">No settlements computed yet</td></tr>'}</tbody></table>`;
}

async function computeSettlements() {
  try {
    await api('/api/settlements/compute', { method: 'POST', body: JSON.stringify({ period_start: $('#setStart').value, period_end: $('#setEnd').value }) });
    toast('Commission settlements computed');
    loadSettlements();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- debt management ---------------- */
async function renderDebt() {
  const isAdmin = state.user.access_level === 'COUNCIL_ADMIN';
  setPage(`
    ${isAdmin ? `<div class="toolbar"><div class="grow"></div><button class="btn-primary" onclick="refreshDebt()">Refresh Ageing</button></div>` : ''}
    <div class="card"><div class="table-wrap" id="debtTable"><div class="empty">Loading…</div></div></div>
  `);
  await loadDebt();
}

async function loadDebt() {
  const isAdmin = state.user.access_level === 'COUNCIL_ADMIN';
  let rows;
  try { rows = await api('/api/debt'); } catch (e) { $('#debtTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#debtTable').innerHTML = `
    <table><thead><tr><th>Bill</th><th>Payer</th><th class="r">Balance</th><th>Ageing</th><th>Stage</th><th class="r">Reminders</th>${isAdmin ? '<th></th>' : ''}</tr></thead>
    <tbody>${rows.map(d => `
      <tr><td class="num">${esc(d.bill_ref)}</td><td>${esc(d.full_name)}</td><td class="r num">${money(d.balance)}</td>
        <td><span class="tag ${d.ageing_bucket === 'OVER_90' ? 'bad' : d.ageing_bucket === '0_30' ? 'ok' : 'warn'}">${esc(d.ageing_bucket.replace('_', '–'))}</span></td>
        <td>${esc(d.enforcement_stage.replace('_', ' '))}</td><td class="r">${d.reminder_count}</td>
        ${isAdmin ? `<td><button class="btn-ghost btn-sm" onclick="escalateDebt(${d.debt_id})" ${d.enforcement_stage === 'CLOSED' ? 'disabled' : ''}>Escalate</button></td>` : ''}</tr>`).join('') || `<tr><td colspan="${isAdmin ? 7 : 6}" class="empty">No open debt cases</td></tr>`}</tbody></table>`;
}

async function refreshDebt() {
  try {
    const r = await api('/api/debt/refresh', { method: 'POST' });
    toast(`${r.cases_opened} new case(s) opened`);
    loadDebt();
  } catch (e) { toast(e.message, true); }
}
async function escalateDebt(id) {
  try {
    const r = await api(`/api/debt/${id}/escalate`, { method: 'POST' });
    toast(`Case escalated to ${r.enforcement_stage.replace('_', ' ')}`);
    loadDebt();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- revenue items ---------------- */
async function renderRevenueItems() {
  setPage('<div class="card"><div class="table-wrap" id="riTable"><div class="empty">Loading…</div></div></div>');
  let rows;
  try { rows = await api('/api/revenue-items'); } catch (e) { $('#riTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#riTable').innerHTML = `
    <table><thead><tr><th>Code</th><th>Item</th><th>Category</th><th>Unit</th><th class="r">Current Rate</th><th>In Scope</th><th></th></tr></thead>
    <tbody>${rows.map(i => `
      <tr><td class="num">${esc(i.harmonised_code)}</td><td>${esc(i.item_name)}</td><td>${esc(i.category_name)}</td>
        <td>${esc(i.unit_of_charge || '—')}</td><td class="r num">${i.current_rate != null ? money(i.current_rate) : '—'}</td>
        <td><span class="tag ${i.in_initial_scope ? 'ok' : 'neutral'}">${i.in_initial_scope ? 'Yes' : 'No'}</span></td>
        <td><button class="btn-ghost btn-sm" onclick="openRateForm(${i.revenue_item_id}, '${esc(i.item_name)}', ${i.current_rate || 0})">Change Rate</button></td></tr>`).join('') || '<tr><td colspan="7" class="empty">No revenue items</td></tr>'}</tbody></table>`;
}

function openRateForm(itemId, itemName, currentRate) {
  openModal(`Change Rate — ${itemName}`, `
    <div class="field"><label>New rate amount</label><input id="rf_amount" type="number" value="${currentRate}" step="1"></div>
    <div class="field"><label>Approval reference</label><input id="rf_ref" placeholder="e.g. Council resolution ref"></div>
    <div class="card-note">The current rate closes out today and this becomes effective immediately. History is kept, not overwritten.</div>
    <div id="rf_err"></div>
  `, `<button class="btn-ghost" onclick="closeModal()">Cancel</button><button class="btn-primary" onclick="submitRateForm(${itemId})">Save Rate</button>`);
}

async function submitRateForm(itemId) {
  const amount = Number($('#rf_amount').value);
  if (!amount || amount <= 0) { $('#rf_err').innerHTML = '<div class="notice bad">Enter a valid rate amount</div>'; return; }
  try {
    await api(`/api/revenue-items/${itemId}/rate`, {
      method: 'POST',
      body: JSON.stringify({ rate_amount: amount, approved_by_ref: $('#rf_ref').value.trim() || undefined }),
    });
    closeModal();
    toast('Rate updated');
    renderRevenueItems();
  } catch (e) { $('#rf_err').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
}

/* ---------------- consultants ---------------- */
async function renderConsultants() {
  const isAdmin = state.user.access_level === 'COUNCIL_ADMIN';
  setPage(`
    ${isAdmin ? `<div class="toolbar"><div class="grow"></div><button class="btn-primary" onclick="openConsultantForm()">Onboard Consultant</button></div>` : ''}
    <div class="card"><div class="table-wrap" id="consTable"><div class="empty">Loading…</div></div></div>
  `);
  let rows;
  try { rows = await api('/api/consultants'); } catch (e) { $('#consTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#consTable').innerHTML = `
    <table><thead><tr><th>Consultant</th><th>Code</th><th class="r">Commission Rate</th><th class="r">Agents</th><th>Status</th><th></th>${isAdmin ? '<th></th>' : ''}</tr></thead>
    <tbody>${rows.map(c => `
      <tr><td>${esc(c.consultant_name)}</td><td class="num">${esc(c.consultant_code)}</td>
        <td class="r num">${c.commission_rate}%</td><td class="r">${c.agents}</td>
        <td><span class="tag ${c.status === 'ACTIVE' ? 'ok' : c.status === 'SUSPENDED' ? 'bad' : 'neutral'}">${esc(c.status)}</span></td>
        <td><button class="btn-ghost btn-sm" onclick="openConsultantPortfolio(${c.consultant_id}, '${esc(c.consultant_name)}')">Portfolio</button></td>
        ${isAdmin ? `<td>
          <select onchange="changeConsultantStatus(${c.consultant_id}, this.value)" style="width:auto">
            ${['PENDING', 'ACTIVE', 'SUSPENDED', 'EXITED'].map(s => `<option value="${s}" ${s === c.status ? 'selected' : ''}>${s}</option>`).join('')}
          </select></td>` : ''}</tr>`).join('') || `<tr><td colspan="${isAdmin ? 7 : 6}" class="empty">No consultants onboarded</td></tr>`}</tbody></table>`;
}

async function changeConsultantStatus(id, status) {
  try {
    await api(`/api/consultants/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) });
    toast('Status updated');
    renderConsultants();
  } catch (e) { toast(e.message, true); }
}

function openConsultantForm() {
  openModal('Onboard Consultant', `
    <div class="field"><label>Consultant name</label><input id="cf_name"></div>
    <div class="row">
      <div class="field"><label>Contract reference</label><input id="cf_ref" placeholder="KAC/RC/2026/xxx"></div>
      <div class="field" style="max-width:160px"><label>Commission rate (%)</label><input id="cf_rate" type="number" value="30" step="0.5"></div>
    </div>
    <div id="cf_err"></div>
  `, `<button class="btn-ghost" onclick="closeModal()">Cancel</button><button class="btn-primary" onclick="submitConsultantForm()">Onboard</button>`);
}

async function submitConsultantForm() {
  const name = $('#cf_name').value.trim();
  if (!name) { $('#cf_err').innerHTML = '<div class="notice bad">Enter the consultant\'s name</div>'; return; }
  try {
    const r = await api('/api/consultants', {
      method: 'POST',
      body: JSON.stringify({ consultant_name: name, contract_ref: $('#cf_ref').value.trim(), commission_rate: Number($('#cf_rate').value) || 0 }),
    });
    closeModal();
    toast(`Consultant onboarded — ${r.consultant_code}`);
    renderConsultants();
  } catch (e) { $('#cf_err').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
}

async function openConsultantPortfolio(consultantId, consultantName) {
  const isAdmin = state.user.access_level === 'COUNCIL_ADMIN';
  openModal(`Portfolio — ${consultantName}`, '<div class="empty">Loading…</div>');
  let portfolio, items;
  try {
    [portfolio, items] = await Promise.all([
      api(`/api/consultants/${consultantId}/portfolio`),
      isAdmin ? api('/api/revenue-items') : Promise.resolve([]),
    ]);
  } catch (e) { $('#modalBody').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }

  const assignedIds = new Set(portfolio.map(p => p.revenue_item_id));
  const rows = portfolio.map(p => `
    <div class="kv"><span>${esc(p.harmonised_code)} — ${esc(p.item_name)}${p.ward_name ? ' · ' + esc(p.ward_name) : ''}</span>
      <b>${isAdmin ? `<a href="javascript:void(0)" onclick="revokeConsultantPortfolio(${consultantId}, ${p.portfolio_id})" style="color:var(--danger);font-weight:400">revoke</a>` : ''}</b></div>
  `).join('') || '<div class="empty">No revenue items assigned yet</div>';

  const addForm = isAdmin ? `
    <div class="row" style="margin-top:16px;border-top:1px solid var(--line);padding-top:14px">
      <div class="field"><label>Add revenue item</label>
        <select id="pf_item">${items.filter(i => !assignedIds.has(i.revenue_item_id)).map(i => `<option value="${i.revenue_item_id}">${esc(i.harmonised_code)} — ${esc(i.item_name)}</option>`).join('')}</select>
      </div>
      <div class="field" style="max-width:140px"><label>&nbsp;</label><button class="btn-ghost" style="width:100%" onclick="addConsultantPortfolio(${consultantId}, '${esc(consultantName)}')">Add</button></div>
    </div>` : '';

  $('#modalBody').innerHTML = `<h3 style="margin-bottom:10px">Assigned revenue items (${portfolio.length})</h3>${rows}${addForm}`;
  $('#modalFoot').innerHTML = `<button class="btn-ghost" onclick="closeModal()">Close</button>`;
}

async function addConsultantPortfolio(consultantId, consultantName) {
  const itemId = $('#pf_item').value;
  if (!itemId) { toast('No revenue items left to add', true); return; }
  try {
    await api(`/api/consultants/${consultantId}/portfolio`, { method: 'POST', body: JSON.stringify({ revenue_item_id: itemId }) });
    toast('Revenue item assigned');
    openConsultantPortfolio(consultantId, consultantName);
  } catch (e) { toast(e.message, true); }
}

async function revokeConsultantPortfolio(consultantId, portfolioId) {
  try {
    await api(`/api/consultants/${consultantId}/portfolio/${portfolioId}/end`, { method: 'POST' });
    toast('Assignment revoked');
    const name = $('#modalTitle').textContent.replace('Portfolio — ', '');
    openConsultantPortfolio(consultantId, name);
  } catch (e) { toast(e.message, true); }
}

/* ---------------- agents ---------------- */
async function renderAgents() {
  setPage(`
    <div class="toolbar"><div class="grow"></div><button class="btn-primary" onclick="openAgentForm()">Onboard Agent</button></div>
    <div class="card"><div class="table-wrap" id="agentTable"><div class="empty">Loading…</div></div></div>
  `);
  let rows;
  try { rows = await api('/api/agents'); } catch (e) { $('#agentTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#agentTable').innerHTML = `
    <table><thead><tr><th>Code</th><th>Name</th><th>Phone</th><th>Ward</th><th>Consultant</th><th class="r">Lifetime Collected</th><th>Status</th><th></th></tr></thead>
    <tbody>${rows.map(a => `
      <tr><td class="num">${esc(a.agent_code)}</td><td>${esc(a.full_name)}</td><td class="num">${esc(a.phone || '—')}</td>
        <td>${esc(a.ward_name || '—')}</td><td>${esc(a.consultant_name || '—')}</td>
        <td class="r num">${money(a.lifetime_collected)}</td>
        <td><span class="tag ${a.status === 'ACTIVE' ? 'ok' : 'neutral'}">${esc(a.status)}</span></td>
        <td><button class="btn-ghost btn-sm" onclick="openAgentActivity(${a.agent_id}, '${esc(a.full_name)}')">Activity</button></td></tr>`).join('') || '<tr><td colspan="8" class="empty">No field agents</td></tr>'}</tbody></table>`;
}

async function openAgentForm() {
  const isAdmin = state.user.access_level === 'COUNCIL_ADMIN';
  let wards = [], consultants = [];
  try {
    wards = await api('/api/wards');
    if (isAdmin) consultants = await api('/api/consultants');
  } catch {}
  openModal('Onboard Agent', `
    <div class="row"><div class="field"><label>Full name</label><input id="af_name"></div>
      <div class="field"><label>Username</label><input id="af_username" placeholder="e.g. agent13"></div></div>
    <div class="row"><div class="field"><label>Phone</label><input id="af_phone"></div>
      <div class="field"><label>Ward</label><select id="af_ward"><option value="">—</option>${wards.map(w => `<option value="${w.ward_id}">${esc(w.ward_name)}</option>`).join('')}</select></div></div>
    ${isAdmin ? `<div class="field"><label>Consultant</label><select id="af_consultant"><option value="">Council-direct (no consultant)</option>${consultants.map(c => `<option value="${c.consultant_id}">${esc(c.consultant_name)}</option>`).join('')}</select></div>` : ''}
    <div class="card-note">Default password is <b>revac2026</b> — the agent should change it after first sign-in.</div>
    <div id="af_err"></div>
  `, `<button class="btn-ghost" onclick="closeModal()">Cancel</button><button class="btn-primary" onclick="submitAgentForm()">Onboard</button>`);
}

async function submitAgentForm() {
  const name = $('#af_name').value.trim();
  const username = $('#af_username').value.trim();
  if (!name || !username) { $('#af_err').innerHTML = '<div class="notice bad">Enter a name and a username</div>'; return; }
  const body = { full_name: name, username, phone: $('#af_phone').value.trim(), assigned_ward_id: $('#af_ward').value || null };
  if ($('#af_consultant')) body.consultant_id = $('#af_consultant').value || null;
  try {
    const r = await api('/api/agents', { method: 'POST', body: JSON.stringify(body) });
    closeModal();
    toast(`Agent onboarded — ${r.agent_code}`);
    renderAgents();
  } catch (e) { $('#af_err').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
}

async function openAgentActivity(agentId, name) {
  openModal(`Activity — ${name}`, '<div class="empty">Loading…</div>');
  let d;
  try { d = await api(`/api/agents/${agentId}/activity`); } catch (e) { $('#modalBody').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#modalBody').innerHTML = `
    <h3 style="margin-bottom:8px">Daily Returns (last 30 days)</h3>
    <div class="table-wrap">${d.daily_returns.length ? `<table><thead><tr><th>Date</th><th class="r">Visits</th><th class="r">Bills Issued</th><th class="r">Collected</th></tr></thead>
      <tbody>${d.daily_returns.map(r => `<tr><td class="num">${d10(r.return_date)}</td><td class="r">${r.visits_count}</td><td class="r">${r.bills_issued}</td><td class="r num">${money(r.amount_collected)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">No daily returns recorded</div>'}</div>
    <h3 style="margin:18px 0 8px">Recent Payments</h3>
    <div class="table-wrap">${d.recent_payments.length ? `<table><thead><tr><th>Payment Ref</th><th>Bill</th><th>Channel</th><th class="r">Amount</th><th>Paid At</th></tr></thead>
      <tbody>${d.recent_payments.map(p => `<tr><td class="num">${esc(p.payment_ref)}</td><td class="num">${esc(p.bill_ref)}</td><td>${esc(p.channel_name)}</td><td class="r num">${money2(p.amount)}</td><td class="num">${dt(p.paid_at)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">No payments recorded</div>'}</div>
  `;
  $('#modalFoot').innerHTML = `<button class="btn-ghost" onclick="closeModal()">Close</button>`;
}

/* ---------------- terminals ---------------- */
async function renderTerminals() {
  setPage('<div class="card"><div class="table-wrap" id="termTable"><div class="empty">Loading…</div></div></div>');
  let rows;
  try { rows = await api('/api/terminals'); } catch (e) { $('#termTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#termTable').innerHTML = `
    <table><thead><tr><th>Serial</th><th>Bank TID</th><th>Agent</th><th>Ward</th><th class="r">Collected</th><th>Status</th></tr></thead>
    <tbody>${rows.map(t => `
      <tr><td class="num">${esc(t.terminal_serial)}</td><td class="num">${esc(t.bank_terminal_id || '—')}</td>
        <td>${esc(t.agent_name || '—')}</td><td>${esc(t.ward_name || '—')}</td>
        <td class="r num">${money(t.collected)}</td>
        <td><span class="tag ${t.status === 'ACTIVE' ? 'ok' : t.status === 'FAULTY' ? 'bad' : 'neutral'}">${esc(t.status)}</span></td></tr>`).join('') || '<tr><td colspan="6" class="empty">No terminals deployed</td></tr>'}</tbody></table>`;
}

/* ---------------- audit log ---------------- */
async function renderAudit() {
  setPage('<div class="card"><div class="table-wrap" id="auditTable"><div class="empty">Loading…</div></div></div>');
  let rows;
  try { rows = await api('/api/audit'); } catch (e) { $('#auditTable').innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
  $('#auditTable').innerHTML = `
    <table><thead><tr><th>When</th><th>User</th><th>Action</th><th>Entity</th><th>IP</th></tr></thead>
    <tbody>${rows.map(a => `
      <tr><td class="num">${dt(a.occurred_at)}</td><td>${esc(a.full_name || 'system')}</td>
        <td><span class="tag brass">${esc(a.action)}</span></td>
        <td class="num">${esc(a.entity_type)}${a.entity_id ? ' #' + a.entity_id : ''}</td>
        <td class="num">${esc(a.ip_address || '—')}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">No audit events yet</td></tr>'}</tbody></table>`;
}

/* ---------------- start ---------------- */
(function () {
  const saved = store.load();
  if (saved?.token) { state.token = saved.token; state.user = saved.user; boot(); }
  document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && $('#login').style.display !== 'none' && document.activeElement && ['u', 'p'].includes(document.activeElement.id)) doLogin();
  });
})();
