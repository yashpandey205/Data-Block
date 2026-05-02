// ============================================================================
// Lightweight Blockchain Dashboard — Frontend Logic
// ============================================================================
// Connects to the Flask API and renders live blockchain data.
// ============================================================================

const API = window.location.origin;
let currentNodePort = parseInt(window.location.port) || 5001;
let refreshInterval = null;

// ---------- Initialization ----------

document.addEventListener('DOMContentLoaded', () => {
    setupNodeSelector();
    refreshAll();
    startAutoRefresh();
});

function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(refreshAll, 4000);
}

function refreshAll() {
    fetchStatus();
    fetchChain();
    fetchPending();
    fetchNodes();
}

// ---------- Node Selector ----------

function setupNodeSelector() {
    const sel = document.getElementById('nodeSelector');
    if (sel) {
        sel.value = currentNodePort;
        sel.addEventListener('change', (e) => {
            currentNodePort = parseInt(e.target.value);
            refreshAll();
        });
    }
}

function api(path) {
    return `http://127.0.0.1:${currentNodePort}${path}`;
}

// ---------- API Calls ----------

async function fetchStatus() {
    try {
        const res = await fetch(api('/status'));
        const data = await res.json();

        setText('statChainLen', data.chain_length);
        setText('statPending', data.pending_transactions);
        setText('statValid', data.chain_valid ? '✔ Valid' : '✘ Invalid');
        setText('statNodeId', data.node_id);
        setText('headerNodeId', data.node_id);
        setText('statPubkey', data.public_key ? data.public_key.substring(0, 20) + '…' : '—');

        // PBFT info
        const pbft = data.pbft || {};
        setText('pbftNodes', pbft.total_nodes || '—');
        setText('pbftFault', pbft.fault_tolerance || '—');
        setText('pbftPrepTh', pbft.prepare_threshold || '—');
        setText('pbftCommitTh', pbft.commit_threshold || '—');

        const rounds = pbft.active_rounds || {};
        const roundCount = Object.keys(rounds).length;
        setText('statRounds', roundCount);

        // Update PBFT rounds list
        const roundsEl = document.getElementById('pbftRounds');
        if (roundsEl) {
            if (roundCount === 0) {
                roundsEl.innerHTML = '<div class="empty-state"><div class="icon">⏳</div>No active consensus rounds</div>';
            } else {
                roundsEl.innerHTML = Object.entries(rounds).map(([hash, r]) => `
                    <div class="tx-item">
                        <div class="tx-row">
                            <span class="tx-label">Block ${r.block_index}</span>
                            <span class="card-badge badge-${r.status === 'committed' ? 'success' : r.status === 'prepared' ? 'info' : 'warning'}">${r.status}</span>
                        </div>
                        <div class="tx-row">
                            <span class="tx-label">Hash</span>
                            <span class="tx-value">${hash}…</span>
                        </div>
                        <div class="tx-row">
                            <span class="tx-label">Prepares / Commits</span>
                            <span class="tx-value">${r.prepares} / ${r.commits}</span>
                        </div>
                    </div>
                `).join('');
            }
        }
    } catch (e) {
        setText('statChainLen', '—');
        setText('statValid', '—');
    }
}

async function fetchChain() {
    try {
        const res = await fetch(api('/chain'));
        const data = await res.json();
        const chain = data.chain || [];

        const listEl = document.getElementById('blockList');
        if (!listEl) return;

        if (chain.length === 0) {
            listEl.innerHTML = '<div class="empty-state"><div class="icon">📦</div>No blocks yet</div>';
            return;
        }

        listEl.innerHTML = chain.slice().reverse().map(block => {
            const isGenesis = block.index === 0;
            const txCount = block.transactions.length;
            const time = block.timestamp === 0 ? 'Genesis' : new Date(block.timestamp * 1000).toLocaleTimeString();

            let txHtml = '';
            if (txCount > 0) {
                txHtml = `<div class="block-txns">
                    <div style="font-size:11px;color:var(--text-muted);font-weight:600;margin-bottom:4px;">TRANSACTIONS</div>
                    ${block.transactions.map(tx => `
                        <div class="tx-item">
                            <div class="tx-row">
                                <span class="tx-label">From</span>
                                <span class="tx-value">${tx.sender}</span>
                            </div>
                            <div class="tx-row">
                                <span class="tx-label">To</span>
                                <span class="tx-value">${tx.receiver}</span>
                            </div>
                            <div class="tx-row">
                                <span class="tx-label">TX ID</span>
                                <span class="tx-value">${tx.tx_id.substring(0, 24)}…</span>
                            </div>
                            <div class="tx-row">
                                <span class="tx-label">Encrypted Data</span>
                                <span class="tx-value">${tx.encrypted_data.substring(0, 30)}…</span>
                            </div>
                            <div style="margin-top:6px;">
                                <button class="btn btn-success btn-sm" onclick="decryptFromChain('${escapeHtml(tx.encrypted_data)}', '${escapeHtml(tx.encrypted_aes_key)}')">
                                    🔓 Decrypt
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>`;
            }

            return `
                <div class="block-item ${isGenesis ? 'genesis' : ''}">
                    <div class="block-header-row">
                        <span class="block-index">${isGenesis ? '🏁 Genesis Block' : '⛓ Block #' + block.index}</span>
                        <span class="block-tx-count">${txCount} txn${txCount !== 1 ? 's' : ''} · ${time}</span>
                    </div>
                    <div class="block-detail-row">
                        <div class="block-hash"><span>Hash:</span>${block.hash.substring(0, 32)}…</div>
                    </div>
                    <div class="block-detail-row">
                        <div class="block-prev-hash"><span>Prev:</span>${block.previous_hash.substring(0, 32)}…</div>
                    </div>
                    ${block.merkle_root ? `<div class="block-detail-row"><div class="block-merkle"><span>Merkle:</span>${block.merkle_root.substring(0, 32)}…</div></div>` : ''}
                    ${txHtml}
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('fetchChain error', e);
    }
}

async function fetchPending() {
    try {
        const res = await fetch(api('/pending'));
        const data = await res.json();
        const txns = data.pending_transactions || [];
        setText('statPending', txns.length);
    } catch (e) { /* ignore */ }
}

async function fetchNodes() {
    try {
        const res = await fetch(api('/nodes'));
        const data = await res.json();
        const nodes = data.nodes || {};

        const grid = document.getElementById('nodesGrid');
        if (!grid) return;

        grid.innerHTML = Object.entries(nodes).map(([id, cfg]) => {
            const isCurrent = cfg.api_port === currentNodePort;
            return `
                <div class="node-card ${isCurrent ? 'active-node' : ''}">
                    <div class="node-card-header">
                        <span class="node-name">${id}</span>
                        <span class="node-status-icon">${isCurrent ? '🟢' : '⚪'}</span>
                    </div>
                    <div class="node-detail">API: ${cfg.host}:${cfg.api_port}</div>
                    <div class="node-detail">P2P: ${cfg.host}:${cfg.socket_port}</div>
                </div>
            `;
        }).join('');
    } catch (e) { /* ignore */ }
}

// ---------- Submit Transaction ----------

async function submitTransaction() {
    const sender = document.getElementById('txSender').value.trim();
    const receiver = document.getElementById('txReceiver').value.trim();
    const data = document.getElementById('txData').value.trim();

    if (!sender || !receiver || !data) {
        showToast('Please fill in all fields', 'error');
        return;
    }

    const btn = document.getElementById('submitTxBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Broadcasting…';

    try {
        const res = await fetch(api('/transactions/new'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sender, receiver, data }),
        });
        const result = await res.json();

        if (res.ok) {
            showToast(`Transaction broadcasted! TX: ${result.tx_id.substring(0, 16)}…`, 'success');
            document.getElementById('txSender').value = '';
            document.getElementById('txReceiver').value = '';
            document.getElementById('txData').value = '';
            setTimeout(refreshAll, 2000);
        } else {
            showToast(result.error || 'Failed to submit', 'error');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🚀 Encrypt & Broadcast';
    }
}

// ---------- Decrypt ----------

async function decryptData() {
    const encData = document.getElementById('decEncData').value.trim();
    const encKey = document.getElementById('decEncKey').value.trim();

    if (!encData || !encKey) {
        showToast('Please provide both encrypted data and key', 'error');
        return;
    }

    const btn = document.getElementById('decryptBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Decrypting…';

    try {
        const res = await fetch(api('/decrypt'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ encrypted_data: encData, encrypted_aes_key: encKey }),
        });
        const result = await res.json();
        const resultEl = document.getElementById('decryptResult');

        if (result.plaintext) {
            resultEl.innerHTML = `
                <div class="decrypt-result">
                    <h4>🔓 Decrypted Plaintext</h4>
                    <p>${escapeHtml(result.plaintext)}</p>
                </div>`;
        } else {
            resultEl.innerHTML = `
                <div class="decrypt-result error">
                    <h4>⚠ Decryption Failed</h4>
                    <p>${escapeHtml(result.error || 'Unknown error')}</p>
                </div>`;
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🔓 Decrypt Data';
    }
}

function decryptFromChain(encData, encKey) {
    document.getElementById('decEncData').value = encData;
    document.getElementById('decEncKey').value = encKey;
    document.getElementById('decEncData').scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(decryptData, 300);
}

// ---------- Validate Chain ----------

async function validateChain() {
    try {
        const res = await fetch(api('/validate'));
        const data = await res.json();
        if (data.is_valid) {
            showToast(`Chain is VALID (${data.chain_length} blocks)`, 'success');
        } else {
            showToast('Chain integrity check FAILED!', 'error');
        }
    } catch (e) {
        showToast('Validation error: ' + e.message, 'error');
    }
}

// ---------- Utilities ----------

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${type === 'success' ? '✔' : '⚠'}</span> ${escapeHtml(message)}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}
