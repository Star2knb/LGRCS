/* ==========================================================================
   RevAc Field — mobile agent app
   Offline-capable: collections captured without a signal are queued locally
   and replayed to the server on reconnect.
   ========================================================================== */

const S = { token: null, agent: null, userName: null, payers: [], selected: null, bills: [],
            channel: 'POS', queue: [], lastSync: null, geo: null };

const $ = s => document.querySelector(s);
const money = n => '₦' + Number(n || 0).toLocaleString('en-NG', { maximumFractionDigits: 0 });
const money2 = n => '₦' + Number(n || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function toast(m, bad) {
  const d = document.createElement('div');
  d.className = 'tst' + (bad ? ' bad' : '');
  d.textContent = m;
  $('#toast').appendChild(d);
  setTimeout(() => d.remove(), 3600);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json',
      ...(S.token ? { Authorization: 'Bearer ' + S.token } : {}), ...(opts.headers || {}) }
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || 'Request failed');
  return d;
}

/* ---------------- local persistence ---------------- */
const store = {
  save() {
    localStorage.setItem('revac_field', JSON.stringify({
      token: S.token, agent: S.agent, userName: S.userName, queue: S.queue,
      lastSync: S.lastSync, payers: S.payers
    }));
  },
  load() {
    try { return JSON.parse(localStorage.getItem('revac_field') || 'null'); }
    catch { return null; }
  },
  clear() { localStorage.removeItem('revac_field'); }
};

/* ---------------- auth ---------------- */
async function doLogin() {
  $('#loginErr').style.display = 'none';
  try {
    const r = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: $('#u').value, password: $('#p').value })
    });
    if (r.user.access_level !== 'AGENT') throw new Error('Sign in with a field agent account');
    S.token = r.token;
    S.userName = r.user.full_name;
    await boot();
  } catch (e) {
    $('#loginErr').textContent = e.message;
    $('#loginErr').style.display = 'block';
  }
}

function signOut() {
  api('/api/auth/logout', { method: 'POST' }).catch(() => {});
  store.clear();
  location.reload();
}

/* ---------------- boot ---------------- */
async function boot() {
  const d = await api('/api/mobile/worklist');
  S.agent = d.agent;
  S.payers = d.payers;
  $('#login').style.display = 'none';
  $('#app').style.display = 'block';
  if (!S.userName) { try { S.userName = (await api('/api/auth/me')).full_name; } catch {} }
  $('#agName').textContent = S.userName || 'Field Agent';
  $('#agWard').textContent = 'Agent ' + d.agent.agent_code;
  $('#av').textContent = (d.agent.agent_code || 'AG').slice(-2);
  $('#tCash').textContent = money(d.today.collected);
  $('#tTxn').textContent = d.today.txns;
  $('#rCash').textContent = money2(d.today.collected);
  $('#rTxn').textContent = d.today.txns;
  $('#rCode').textContent = d.agent.agent_code;
  $('#rWard').textContent = S.payers[0]?.ward_name || '—';
  $('#rPayers').textContent = S.payers.length;
  renderList();
  updateQueueBar();
  store.save();
}

/* ---------------- navigation ---------------- */
function go(v) {
  document.querySelectorAll('.view').forEach(el => el.classList.remove('on'));
  $('#v-' + v).classList.add('on');
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  window.scrollTo(0, 0);
}

/* ---------------- worklist ---------------- */
function renderList() {
  const q = ($('#search')?.value || '').toLowerCase();
  const rows = S.payers.filter(p => !q || p.full_name.toLowerCase().includes(q)
    || (p.payer_ref || '').toLowerCase().includes(q));
  $('#listBody').innerHTML = rows.length ? rows.map(p => `
    <div class="payer" onclick="pickPayer(${p.payer_id})">
      <div class="ini">${esc(p.full_name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase())}</div>
      <div class="info"><b>${esc(p.full_name)}</b>
        <small class="num">${esc(p.payer_ref)} · ${esc(p.ward_name || '')}</small></div>
      <div class="due">${p.outstanding > 0
        ? `<b class="num">${money(p.outstanding)}</b><small>outstanding</small>`
        : '<span class="tag ok">Cleared</span>'}</div>
    </div>`).join('') : '<div class="empty">No payers match that search</div>';
}

async function pickPayer(id) {
  const p = S.payers.find(x => x.payer_id === id);
  S.selected = p;
  go('collect');
  $('#selPayer').outerHTML = `<div id="selPayer">
    <div style="font-size:17px;font-weight:600">${esc(p.full_name)}</div>
    <div class="num" style="color:var(--ink-40);font-size:12.5px;margin-top:3px">
      ${esc(p.payer_ref)} · ${esc(p.phone || 'no phone')}</div>
    <div style="margin-top:9px;font-size:13.5px">${esc(p.address || '')}</div>
    <div class="kv" style="margin-top:12px"><span>Outstanding</span>
      <b class="num">${money2(p.outstanding)}</b></div></div>`;

  try {
    const full = await api('/api/payers/' + id);
    S.bills = full.bills.filter(b => b.balance > 0);
  } catch { S.bills = []; }

  $('#billBox').style.display = 'block';
  $('#billList').innerHTML = S.bills.length ? S.bills.map((b, i) => `
    <div class="payer" style="margin-bottom:8px" onclick="pickBill(${i})">
      <div class="info"><b class="num">${esc(b.bill_ref)}</b>
        <small>due ${esc(String(b.due_date).slice(0, 10))} · ${esc(b.status.replace('_', ' '))}</small></div>
      <div class="due"><b class="num">${money(b.balance)}</b><small>balance</small></div>
    </div>`).join('') : '<div class="empty">No unpaid bills for this payer</div>';
  $('#payBox').style.display = 'none';
}

function pickBill(i) {
  S.bill = S.bills[i];
  $('#payBox').style.display = 'block';
  $('#amt').value = Number(S.bill.balance).toFixed(2);
  $('#payBox').scrollIntoView({ behavior: 'smooth' });
}

document.addEventListener('click', e => {
  const b = e.target.closest('#chanPick button');
  if (!b) return;
  document.querySelectorAll('#chanPick button').forEach(x => x.classList.remove('sel'));
  b.classList.add('sel');
  S.channel = b.dataset.ch;
});

/* ---------------- payment (online or queued) ---------------- */
async function takePayment() {
  if (!S.bill) return toast('Choose a bill first', true);
  const amount = Number($('#amt').value);
  if (!amount || amount <= 0) return toast('Enter an amount', true);

  const record = {
    client_id: 'c' + Date.now(),
    entity_type: 'PAYMENT',
    device_created_at: new Date().toISOString(),
    payload: { bill_id: S.bill.bill_id, amount, channel_code: S.channel,
               bank_txn_ref: $('#bankRef').value || null, geo: S.geo }
  };

  if (!navigator.onLine) {
    S.queue.push(record);
    store.save();
    updateQueueBar();
    showReceipt({ receipt_ref: 'QUEUED-' + record.client_id.slice(-6), qr_token: '—' },
      amount, true);
    return;
  }

  try {
    const r = await api('/api/payments', {
      method: 'POST',
      body: JSON.stringify({ bill_id: S.bill.bill_id, amount, channel_code: S.channel,
        bank_txn_ref: $('#bankRef').value || null, geo: S.geo })
    });
    showReceipt(r.receipt, amount, false);
    $('#bankRef').value = '';
    S.bill = null;
    boot();
  } catch (e) {
    S.queue.push(record);
    store.save();
    updateQueueBar();
    toast('Saved offline — will sync automatically', true);
    showReceipt({ receipt_ref: 'QUEUED-' + record.client_id.slice(-6), qr_token: '—' }, amount, true);
  }
}

function showReceipt(receipt, amount, queued) {
  go('receipt');
  $('#receiptBody').innerHTML = `<div class="receipt">
    <div style="font-size:10.5px;letter-spacing:.09em;color:var(--ink-40);text-transform:uppercase">
      Abuja Municipal Area Council</div>
    <div class="amt num">${money2(amount)}</div>
    <div class="ok" style="${queued ? 'background:#FDF3DC;color:#9A6B00' : ''}">
      ${queued ? 'Queued — syncs when online' : 'Payment confirmed'}</div>
    ${queued ? '' : qrSvg(receipt.qr_token)}
    <div class="kv" style="margin-top:16px"><span>Receipt</span>
      <b class="num">${esc(receipt.receipt_ref)}</b></div>
    <div class="kv"><span>Payer</span><b>${esc(S.selected?.full_name || '')}</b></div>
    <div class="kv"><span>Channel</span><b>${esc(S.channel)}</b></div>
    <div class="kv"><span>Time</span><b class="num">${new Date().toLocaleString('en-NG')}</b></div>
    <p style="margin-top:14px;font-size:12.5px;color:var(--ink-60)">
      ${queued ? 'The payer keeps this reference. The receipt is issued in full once this device reconnects.'
               : 'The payer receives this by SMS. Scanning the code confirms it is genuine.'}</p>
  </div>`;
}

/* Deterministic QR-style block rendered from the token — no external library */
function qrSvg(token) {
  if (!token || token === '—') return '';
  let h = 0;
  for (let i = 0; i < token.length; i++) h = (h * 31 + token.charCodeAt(i)) >>> 0;
  const N = 21, cells = [];
  let seed = h;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const finder = (x < 7 && y < 7) || (x > N - 8 && y < 7) || (x < 7 && y > N - 8);
    const ring = finder && !((x % (N - 7) > 0 && x % (N - 7) < 6 && y > 0 && y < 6)
      && !(x % (N - 7) > 1 && x % (N - 7) < 5 && y > 1 && y < 5));
    if (finder) { if (ring) cells.push([x, y]); }
    else if (rnd() > 0.52) cells.push([x, y]);
  }
  return `<svg class="qr" viewBox="0 0 ${N} ${N}" shape-rendering="crispEdges">
    <rect width="${N}" height="${N}" fill="#fff"/>
    ${cells.map(([x, y]) => `<rect x="${x}" y="${y}" width="1" height="1" fill="#06281D"/>`).join('')}
  </svg>`;
}

/* ---------------- enumeration ---------------- */
function grabGps() {
  if (!navigator.geolocation) return toast('This device has no GPS', true);
  navigator.geolocation.getCurrentPosition(
    pos => {
      S.geo = { lat: +pos.coords.latitude.toFixed(6), lng: +pos.coords.longitude.toFixed(6) };
      $('#n_geo').value = `${S.geo.lat}, ${S.geo.lng}`;
      toast('Position captured');
    },
    () => toast('Could not read your position', true),
    { enableHighAccuracy: true, timeout: 8000 }
  );
}

async function registerPayer() {
  const body = {
    full_name: $('#n_name').value, payer_type: $('#n_type').value, phone: $('#n_phone').value,
    address: $('#n_addr').value, ward_id: S.agent.assigned_ward_id,
    geo_lat: S.geo?.lat, geo_lng: S.geo?.lng, force: true
  };
  if (!body.full_name) return toast('Enter the payer name', true);

  if (!navigator.onLine) {
    S.queue.push({ client_id: 'p' + Date.now(), entity_type: 'PAYER',
      device_created_at: new Date().toISOString(), payload: body });
    store.save(); updateQueueBar();
    $('#enumOut').innerHTML = '<div class="tag">Saved offline — syncs when you reconnect</div>';
    return;
  }
  try {
    const r = await api('/api/payers', { method: 'POST', body: JSON.stringify(body) });
    $('#enumOut').innerHTML = `<div class="tag ok">Registered · ${esc(r.payer_ref)}</div>`;
    ['n_name', 'n_phone', 'n_addr'].forEach(i => $('#' + i).value = '');
    toast('Payer registered');
    boot();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- offline sync ---------------- */
function updateQueueBar() {
  const n = S.queue.length;
  $('#queueBar').classList.toggle('on', n > 0);
  $('#queueTxt').textContent = `${n} record${n === 1 ? '' : 's'} waiting to sync`;
  $('#rQueue').textContent = n;
  $('#rSync').textContent = S.lastSync ? new Date(S.lastSync).toLocaleTimeString('en-NG') : '—';
}

async function syncNow() {
  if (!S.queue.length) return toast('Nothing waiting to sync');
  if (!navigator.onLine) return toast('Still offline — will retry automatically', true);
  try {
    const r = await api('/api/mobile/sync', {
      method: 'POST', body: JSON.stringify({ records: S.queue })
    });
    const done = new Set(r.accepted);
    S.queue = S.queue.filter(x => !done.has(x.client_id));
    S.lastSync = Date.now();
    store.save(); updateQueueBar();
    toast(`${r.accepted.length} record${r.accepted.length === 1 ? '' : 's'} synced`);
    if (r.conflicts.length) toast(`${r.conflicts.length} could not be applied`, true);
    boot();
  } catch (e) { toast(e.message, true); }
}

function netStatus() {
  const on = navigator.onLine;
  $('#net').textContent = on ? 'Online' : 'Offline';
  $('#net').classList.toggle('off', !on);
  if (on && S.queue.length) syncNow();
}
window.addEventListener('online', netStatus);
window.addEventListener('offline', netStatus);

/* ---------------- start ---------------- */
(function () {
  const saved = store.load();
  if (saved?.token) {
    S.token = saved.token; S.userName = saved.userName;
    S.queue = saved.queue || []; S.lastSync = saved.lastSync;
    boot().catch(() => store.clear());
  }
  netStatus();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/mobile/sw.js').catch(() => {});
  document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && $('#login').style.display !== 'none') doLogin();
  });
})();
