/* app.js — SDS Retrieval Agent frontend logic */
'use strict';

const API = 'http://127.0.0.1:8000';
let _pollTimer = null;
let _products  = [];
let _results   = [];

// ============================================================
// Utility
// ============================================================
const $ = id => document.getElementById(id);

function notify(msg, type = 'info', duration = 4000) {
  const area = $('notification-area');
  const el   = document.createElement('div');
  el.className = `notif ${type}`;
  el.textContent = msg;
  area.prepend(el);
  setTimeout(() => el.remove(), duration);
}

function showToast(msg, type = '', duration = 3500) {
  const t = $('upload-toast');
  t.textContent = msg;
  t.className   = `toast ${type}`;
  t.classList.remove('hidden');
  setTimeout(() => t.classList.add('hidden'), duration);
}

function setStatus(state, text) {
  const dot  = $('status-dot');
  const span = $('status-text');
  dot.className = `status-dot ${state}`;
  span.textContent = text;
}

async function apiFetch(path, opts = {}) {
  const resp = await fetch(API + path, opts);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

function statusBadge(status) {
  const map = {
    pending:   '<span class="badge badge-pending">⏳ Pending</span>',
    running:   '<span class="badge badge-running">🔄 Running</span>',
    found:     '<span class="badge badge-found">✅ Found</span>',
    not_found: '<span class="badge badge-not_found">— Not Found</span>',
    error:     '<span class="badge badge-error">❌ Error</span>',
  };
  return map[status] || `<span class="badge badge-not_found">${status || '—'}</span>`;
}

function truncate(str, n = 40) {
  if (!str) return '—';
  return str.length > n ? str.slice(0, n) + '…' : str;
}

// ============================================================
// Tab navigation
// ============================================================
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${tab}`).classList.add('active');
    if (tab === 'products') loadProducts();
    if (tab === 'results')  loadResults();
    if (tab === 'metrics')  loadMetrics();
  });
});

window.switchTab = function(tabName) {
  const btn = $(`nav-${tabName}`);
  if (btn) btn.click();
};

// ============================================================
// Upload tab
// ============================================================
const dropzone  = $('dropzone');
const fileInput = $('file-input');
const browseBtn = $('browse-btn');

browseBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => { if (fileInput.files[0]) uploadFile(fileInput.files[0]); });

dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f) uploadFile(f);
});
dropzone.addEventListener('click', e => { if (e.target === dropzone || e.target.classList.contains('dropzone-inner')) fileInput.click(); });

async function uploadFile(file) {
  const prog   = $('upload-progress');
  const msg    = $('upload-msg');
  const inner  = dropzone.querySelector('.dropzone-inner');

  inner.classList.add('hidden');
  prog.classList.remove('hidden');
  msg.textContent = `Uploading ${file.name}…`;

  const fd = new FormData();
  fd.append('file', file);

  try {
    const data = await apiFetch('/upload', { method: 'POST', body: fd });
    msg.textContent = `✅ Inserted ${data.inserted} product(s)`;
    showToast(`Uploaded ${data.inserted} products! Switching to Products tab…`, 'success');
    setTimeout(() => {
      $('nav-products').click();
      prog.classList.add('hidden');
      inner.classList.remove('hidden');
    }, 1800);
  } catch (err) {
    msg.textContent = `❌ Upload failed: ${err.message}`;
    showToast(`Upload failed: ${err.message}`, 'error');
    setTimeout(() => {
      prog.classList.add('hidden');
      inner.classList.remove('hidden');
    }, 3000);
  }
}

// ============================================================
// Products tab
// ============================================================
async function loadProducts() {
  try {
    _products = await apiFetch('/products');
    renderProducts(_products);
    syncResultStatuses();
  } catch (e) {
    notify(`Failed to load products: ${e.message}`, 'error');
  }
}

function renderProducts(list) {
  const tbody  = $('products-tbody');
  const empty  = $('products-empty');
  const filter = $('product-search').value.toLowerCase();

  const filtered = list.filter(p =>
    !filter ||
    (p.supplier || '').toLowerCase().includes(filter) ||
    (p.product_name || '').toLowerCase().includes(filter) ||
    (p.part_number || '').toLowerCase().includes(filter) ||
    (p.cas_number || '').toLowerCase().includes(filter)
  );

  if (!filtered.length) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  const resultMap = Object.fromEntries(_results.map(r => [r.product_id, r]));

  tbody.innerHTML = filtered.map(p => {
    const result = resultMap[p.id];
    const status = result ? result.status : 'pending';
    return `
    <tr id="prod-row-${p.id}">
      <td><span class="id-pill">#${p.id}</span></td>
      <td><strong>${p.supplier || '—'}</strong></td>
      <td title="${p.product_name}">${truncate(p.product_name, 32)}</td>
      <td><code>${p.part_number || '—'}</code></td>
      <td><code>${p.cas_number || '—'}</code></td>
      <td>${p.language || 'EN'}</td>
      <td>${p.jurisdiction || 'US'}</td>
      <td>${statusBadge(status)}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn btn-success btn-xs" onclick="runOne(${p.id})" id="run-btn-${p.id}">▶ Find SDS</button>
          <button class="btn btn-outline btn-xs" onclick="openEdit(${p.id})">✏️ Edit</button>
          <button class="btn btn-outline btn-danger btn-xs" onclick="deleteProduct(${p.id})">🗑</button>
          ${result && result.status === 'found' ? `<button class="btn btn-outline btn-xs" onclick="downloadSds(${result.id})">⬇ SDS</button>` : ''}
        </div>
      </td>
    </tr>`;
  }).join('');
}

$('product-search').addEventListener('input', () => renderProducts(_products));

$('refresh-products-btn').addEventListener('click', loadProducts);

$('run-all-btn').addEventListener('click', async () => {
  try {
    setStatus('running', 'Running…');
    const r = await apiFetch('/search', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({}) });
    notify('Batch SDS retrieval started! Results will update automatically.', 'info', 6000);
    startPolling();
  } catch (e) {
    notify(`Error: ${e.message}`, 'error');
  }
});

$('clear-btn').addEventListener('click', async () => {
  if (!confirm('Delete ALL products and results? This cannot be undone.')) return;
  try {
    await apiFetch('/products', { method: 'DELETE' });
    _products = [];
    _results  = [];
    renderProducts([]);
    notify('All products cleared.', 'warning');
  } catch (e) {
    notify(`Error: ${e.message}`, 'error');
  }
});

async function runOne(productId) {
  const btn = $(`run-btn-${productId}`);
  if (btn) { btn.textContent = '…'; btn.disabled = true; }
  try {
    setStatus('running', `Processing #${productId}…`);
    const result = await apiFetch(`/search/sync/${productId}`, { method: 'POST' });
    const status = result.status;
    notify(
      status === 'found'
        ? `✅ SDS found for product #${productId}`
        : `Product #${productId}: ${status} — ${result.error || ''}`,
      status === 'found' ? 'success' : 'warning'
    );
    setStatus(status === 'found' ? 'done' : 'error', status);
    loadProducts();
    loadResults();
  } catch (e) {
    notify(`Error searching product #${productId}: ${e.message}`, 'error');
    setStatus('error', 'Error');
  } finally {
    if (btn) { btn.textContent = '▶ Find SDS'; btn.disabled = false; }
  }
}

async function deleteProduct(id) {
  if (!confirm(`Delete product #${id}?`)) return;
  try {
    await apiFetch(`/products/${id}`, { method: 'DELETE' });
    notify(`Product #${id} deleted.`, 'warning');
    loadProducts();
  } catch (e) {
    notify(`Delete failed: ${e.message}`, 'error');
  }
}

// ============================================================
// Edit modal
// ============================================================
function openEdit(id) {
  const p = _products.find(x => x.id === id);
  if (!p) return;
  $('edit-id').value           = p.id;
  $('edit-supplier').value     = p.supplier || '';
  $('edit-product-name').value = p.product_name || '';
  $('edit-part-number').value  = p.part_number || '';
  $('edit-cas').value          = p.cas_number || '';
  $('edit-language').value     = p.language || 'EN';
  $('edit-jurisdiction').value = p.jurisdiction || 'US';
  $('edit-notes').value        = p.notes || '';
  $('edit-modal').classList.remove('hidden');
}

function closeModal() { $('edit-modal').classList.add('hidden'); }
$('modal-close').addEventListener('click', closeModal);
$('modal-cancel').addEventListener('click', closeModal);
$('edit-modal').addEventListener('click', e => { if (e.target === $('edit-modal')) closeModal(); });

$('modal-save').addEventListener('click', async () => {
  const id = parseInt($('edit-id').value);
  const body = {
    supplier:     $('edit-supplier').value.trim(),
    product_name: $('edit-product-name').value.trim(),
    part_number:  $('edit-part-number').value.trim() || null,
    cas_number:   $('edit-cas').value.trim() || null,
    language:     $('edit-language').value,
    jurisdiction: $('edit-jurisdiction').value,
    notes:        $('edit-notes').value.trim() || null,
  };
  try {
    await apiFetch(`/products/${id}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    notify(`Product #${id} updated.`, 'success');
    closeModal();
    loadProducts();
  } catch (e) {
    notify(`Save failed: ${e.message}`, 'error');
  }
});

// ============================================================
// Results tab
// ============================================================
async function loadResults() {
  try {
    _results = await apiFetch('/results');
    renderResults(_results);
    syncResultStatuses();
  } catch (e) {
    notify(`Failed to load results: ${e.message}`, 'error');
  }
}

function renderResults(list) {
  const grid  = $('results-grid');
  const empty = $('results-empty');
  const filter = ($('results-search').value || '').toLowerCase();

  const filtered = list.filter(r =>
    !filter ||
    (r.supplier || '').toLowerCase().includes(filter) ||
    (r.filename || '').toLowerCase().includes(filter) ||
    (r.status || '').toLowerCase().includes(filter)
  );

  if (!filtered.length) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  // Get product names
  const prodMap = Object.fromEntries(_products.map(p => [p.id, p]));

  grid.innerHTML = filtered.map(r => {
    const prod = prodMap[r.product_id];
    const statusClass = r.status === 'found' ? 'found' : r.status === 'error' ? 'error' : '';
    const dateStr = r.retrieved_at ? new Date(r.retrieved_at).toLocaleString() : '';
    return `
    <div class="result-card ${statusClass}">
      <div class="result-card-header">
        <div>
          <div class="result-card-title">${prod ? truncate(prod.product_name, 40) : `Product #${r.product_id}`}</div>
          <div class="result-card-supplier">🏢 ${r.supplier || prod?.supplier || '—'}</div>
        </div>
        ${statusBadge(r.status)}
      </div>
      <div class="result-card-meta">
        ${r.language ? `<span class="meta-pill">🌐 Lang: ${r.language}</span>` : ''}
        ${r.jurisdiction ? `<span class="meta-pill">📍 Juris: ${r.jurisdiction}</span>` : ''}
        ${r.date_issued ? `<span class="meta-pill">📅 ${r.date_issued}</span>` : ''}
        ${prod?.part_number ? `<span class="meta-pill">🔖 ${prod.part_number}</span>` : ''}
      </div>
      ${r.url ? `<div class="result-card-url">${truncate(r.url, 60)}</div>` : ''}
      ${r.error_msg ? `<div style="font-size:11px;color:var(--danger);margin-bottom:12px">${truncate(r.error_msg, 80)}</div>` : ''}
      <div class="result-card-actions">
        ${r.status === 'found' && r.url ? `
          <button class="btn btn-success btn-xs" onclick="downloadSds(${r.id})">⬇ Download SDS</button>
          <button class="btn btn-outline btn-xs" onclick="openUrl('${r.url}')">🔗 Open URL</button>
        ` : ''}
        ${r.status !== 'found' ? `
          <button class="btn btn-primary btn-xs" onclick="runOne(${r.product_id})">🔄 Retry</button>
        ` : ''}
      </div>
      ${dateStr ? `<div class="result-card-date">${dateStr}</div>` : ''}
    </div>`;
  }).join('');
}

$('results-search').addEventListener('input', () => renderResults(_results));
$('refresh-results-btn').addEventListener('click', loadResults);

function openUrl(url) {
  window.open(url, '_blank', 'noopener,noreferrer');
}

async function downloadSds(resultId) {
  try {
    notify('Downloading SDS…', 'info', 3000);
    const a = document.createElement('a');
    a.href = `${API}/download/${resultId}`;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.click();
  } catch (e) {
    notify(`Download failed: ${e.message}`, 'error');
  }
}

// ============================================================
// Sync result statuses into products table
// ============================================================
function syncResultStatuses() {
  // Mark _products with their latest result status
  const latestByProduct = {};
  for (const r of _results) {
    if (!latestByProduct[r.product_id] ||
        new Date(r.retrieved_at) > new Date(latestByProduct[r.product_id].retrieved_at)) {
      latestByProduct[r.product_id] = r;
    }
  }
  // Re-render with updated status
  renderProducts(_products);
}

// ============================================================
// Progress polling (while a batch run is active)
// ============================================================
function startPolling(interval = 3000) {
  if (_pollTimer) return;
  _pollTimer = setInterval(async () => {
    try {
      const prog = await apiFetch('/progress');
      const running = prog.running || [];
      if (running.length === 0) {
        stopPolling();
        setStatus('done', 'Done');
        notify('All SDS retrievals complete!', 'success', 5000);
        loadProducts();
        loadResults();
      } else {
        setStatus('running', `Running (${running.length} active)`);
        loadResults();
        syncResultStatuses();
      }
    } catch (e) {
      // silently ignore polling errors
    }
  }, interval);
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

// ============================================================
// Evaluation Metrics
// ============================================================
async function loadMetrics() {
  try {
    const data = await apiFetch('/metrics');
    const summary = data.summary || {};
    const suppliers = data.supplier_breakdown || {};

    if ($('metric-rate')) $('metric-rate').textContent = `${summary.success_rate_percent || 0.0}%`;
    if ($('metric-total')) $('metric-total').textContent = summary.processed || 0;
    if ($('metric-found')) $('metric-found').textContent = summary.found || 0;
    if ($('metric-notfound')) $('metric-notfound').textContent = (summary.not_found || 0) + (summary.error || 0);

    const tbody = $('metrics-supplier-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const supKeys = Object.keys(suppliers);
    if (supKeys.length === 0) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">No evaluation data available. Run retrieval first.</td></tr>';
      return;
    }

    for (const sup of supKeys) {
      const stats = suppliers[sup];
      const total = stats.total || 0;
      const found = stats.found || 0;
      const notFound = stats.not_found || 0;
      const rate = total > 0 ? ((found / total) * 100).toFixed(1) : '0.0';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${sup}</strong></td>
        <td>${total}</td>
        <td><span class="badge badge-found">${found}</span></td>
        <td><span class="badge badge-not_found">${notFound}</span></td>
        <td><strong>${rate}%</strong></td>
      `;
      tbody.appendChild(tr);
    }
  } catch (e) {
    console.error('Failed to load metrics:', e);
  }
}

const btnRefreshMetrics = $('btn-refresh-metrics');
if (btnRefreshMetrics) {
  btnRefreshMetrics.addEventListener('click', () => {
    loadMetrics();
    notify('Evaluation metrics refreshed!', 'info');
  });
}

// ============================================================
// Expose globals for inline onclick handlers
// ============================================================
window.runOne      = runOne;
window.openEdit    = openEdit;
window.deleteProduct = deleteProduct;
window.downloadSds = downloadSds;
window.openUrl     = openUrl;
window.loadMetrics = loadMetrics;

// ============================================================
// Boot
// ============================================================
(async function boot() {
  // Load both on start so the status column is ready
  await Promise.allSettled([loadProducts(), loadResults(), loadMetrics()]);
})();
