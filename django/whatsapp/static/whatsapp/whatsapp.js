
'use strict';

const qrModal = document.getElementById('qr-modal');
const qrContent = document.getElementById('qr-content');
const qrStatusEl = document.getElementById('qr-status');
let qrPollTimer = null;

async function connectDevice(deviceId, token, phone) {
  if (!qrModal) return;
  qrModal.classList.remove('hidden');
  qrContent.innerHTML = '<div class="qr-wrap"><span class="spinner"></span> Requesting QR…</div>';
  qrStatusEl.textContent = '';

  try {
    const data = await apiPost('/qr', { type: 'qr', whatsapp: phone }, token);
    if (data.status === false) {
      qrContent.innerHTML = `<div class="alert alert-error">${data.reason || 'Failed'}</div>`;
      return;
    }
    const rawQR = data.qr || data.url;
    if (rawQR) {
      const src = rawQR.startsWith('data:') ? rawQR : `data:image/png;base64,${rawQR}`;
      const img = `<img src="${src}" alt="QR Code">`;
      qrContent.innerHTML = `<div class="qr-wrap">${img}<p class="qr-status">Scan with WhatsApp on your phone</p></div>`;
    } else if (data.code) {
      qrContent.innerHTML = `
        <div class="qr-wrap">
          <div class="qr-code-text">${data.code}</div>
          <p class="qr-status">Enter this pairing code in WhatsApp → Linked Devices</p>
        </div>`;
    } else {
      qrContent.innerHTML = `<div class="alert alert-info">Check worker logs for QR output.</div>`;
    }
    qrPollTimer = setInterval(async () => {
      const d = await apiPost('/device', {}, token);
      if (d.device_status === 'connect') {
        clearInterval(qrPollTimer);
        qrStatusEl.textContent = '✓ Connected!';
        qrContent.innerHTML = '<div class="alert alert-success">Device connected successfully.</div>';
        setTimeout(() => { closeQrModal(); location.reload(); }, 1500);
      }
    }, 3000);
  } catch (e) {
    qrContent.innerHTML = `<div class="alert alert-error">Worker unreachable.</div>`;
  }
}

function closeQrModal() {
  if (qrModal) qrModal.classList.add('hidden');
  clearInterval(qrPollTimer);
}
window.closeQrModal = closeQrModal;

document.querySelectorAll('[data-action=connect]').forEach(btn => {
  btn.addEventListener('click', () => {
    const { deviceId, token, phone } = btn.dataset;
    connectDevice(deviceId, token, phone);
  });
});

document.querySelectorAll('[data-action=disconnect]').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!confirm('Disconnect this device from WhatsApp?')) return;
    const { token } = btn.dataset;
    btn.disabled = true;
    const data = await apiPost('/disconnect', {}, token);
    if (data.status) {
      Toast.ok('Device disconnected.');
      setTimeout(() => location.reload(), 800);
    } else {
      Toast.err(data.reason || 'Failed to disconnect.');
      btn.disabled = false;
    }
  });
});

const addDeviceForm = document.getElementById('add-device-form');
if (addDeviceForm) {
  addDeviceForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const accountToken = addDeviceForm.dataset.accountToken;
    const name = addDeviceForm.querySelector('[name=name]').value.trim();
    const phone = addDeviceForm.querySelector('[name=phone]').value.trim();
    if (!name || !phone) return;

    const btn = addDeviceForm.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Adding…';

    const data = await apiPost('/add-device', { name, device: phone }, accountToken);
    btn.disabled = false;
    btn.textContent = 'Add Device';

    if (data.status) {
      Toast.ok(`Device "${name}" added. Token: ${data.token}`);
      setTimeout(() => location.reload(), 1200);
    } else {
      Toast.err(data.reason || 'Failed to add device.');
    }
  });
}

const sendForm = document.getElementById('send-form');
if (sendForm) {
  const deviceSel = sendForm.querySelector('[name=device]');
  const resultBox = document.getElementById('send-result');

  sendForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = deviceSel.options[deviceSel.selectedIndex]?.dataset.token || '';
    if (!token) { Toast.err('Select a connected device.'); return; }

    const body = {
      target:      sendForm.querySelector('[name=target]').value.trim(),
      message:     sendForm.querySelector('[name=message]').value.trim(),
      delay:       sendForm.querySelector('[name=delay]').value || '0',
      schedule:    sendForm.querySelector('[name=schedule]').value || '0',
      typing:      sendForm.querySelector('[name=typing]')?.checked ? 'true' : 'false',
      followup:    sendForm.querySelector('[name=followup]').value || '0',
      preview:     'true',
    };
    if (!body.target) { Toast.err('Target required.'); return; }

    const btn = sendForm.querySelector('button[type=submit]');
    btn.disabled = true; btn.textContent = 'Sending…';
    const data = await apiPost('/send', body, token);
    btn.disabled = false; btn.textContent = 'Send';

    if (data.status) {
      Toast.ok(`✓ Sent to ${(data.target || []).length} recipient(s).`);
      if (resultBox) resultBox.innerHTML =
        `<div class="alert alert-success">Sent! IDs: ${(data.id||[]).join(', ')}</div>`;
    } else {
      Toast.err(data.reason || 'Send failed.');
      if (resultBox) resultBox.innerHTML =
        `<div class="alert alert-error">${data.reason || 'Failed'}</div>`;
    }
  });

  document.querySelectorAll('[data-tpl]').forEach(btn => {
    btn.addEventListener('click', () => {
      const ta = sendForm.querySelector('[name=message]');
      ta.value = btn.dataset.tpl;
      ta.focus();
    });
  });
}

document.querySelectorAll('[data-action=delete-device]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const { token, name } = btn.dataset;
    if (!confirm(`Delete device "${name}"? This removes it and its message history permanently.`)) return;
    btn.disabled = true;
    const data = await apiPost('/delete-device', {}, token);
    if (data.status) {
      Toast.ok('Device deleted.');
      setTimeout(() => location.reload(), 800);
    } else {
      Toast.err(data.reason || 'Failed to delete.');
      btn.disabled = false;
    }
  });
});

if (qrModal) {
  qrModal.addEventListener('click', (e) => {
    if (e.target === qrModal) closeQrModal();
  });
}

const chatShell = document.getElementById('chat-shell');
if (chatShell) {
  const thread = document.getElementById('chat-thread');
  const listRows = document.getElementById('chat-list-rows');
  const contact = chatShell.dataset.contact;
  const token = chatShell.dataset.token;
  const deviceId = chatShell.dataset.device;
  const deviceFilter = chatShell.dataset.deviceFilter;
  const showAll = chatShell.dataset.showAll === '1';
  const canAttach = chatShell.dataset.canAttach === '1';
  const feedUrl = chatShell.dataset.feed;
  const uploadUrl = chatShell.dataset.upload;
  const syncUrl = chatShell.dataset.sync;
  const csrfToken = () => {
    const m = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
    return m ? decodeURIComponent(m[2]) : '';
  };
  let lastAt = null;
  let pendingUpload = null;

  const esc = (s) => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
  const fmt = (iso) => {
    const d = new Date(iso);
    return d.toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  };
  const scrollDown = () => { if (thread) thread.scrollTop = thread.scrollHeight; };
  const tick = (status) => status === 'delivered' || status === 'read' ? '✓✓' : status === 'sent' ? '✓' : '';

  function addBubble(m) {
    if (!thread || thread.querySelector(`[data-id="${m.id}"]`)) return;
    const el = document.createElement('div');
    el.className = `bubble-${m.direction}`;
    el.dataset.id = m.id;
    const file = m.attachment_url
      ? `<a class="bubble-file" href="${m.attachment_url}" target="_blank" rel="noopener">` +
        `<span class="bubble-file-icon">📎</span><span class="bubble-file-name">${esc(m.filename || 'Attachment')}</span></a>`
      : '';
    const text = m.body ? `<div class="bubble-text">${esc(m.body)}</div>` : '';
    const meta = m.direction === 'out'
      ? `${m.at ? fmt(m.at) : ''} <span class="bubble-tick">${tick(m.status)}</span>`
      : `${m.at ? fmt(m.at) : ''}`;
    el.innerHTML = `${file}${text}<div class="bubble-meta">${meta}</div>`;
    thread.appendChild(el);
  }

  if (thread) {
    const bubbles = thread.querySelectorAll('[data-at]');
    if (bubbles.length) lastAt = bubbles[bubbles.length - 1].dataset.at;
    scrollDown();
  }

  const attachBtn = document.getElementById('chat-attach-btn');
  const attachInput = document.getElementById('chat-attach-input');
  if (canAttach && attachBtn && attachInput) {
    attachBtn.addEventListener('click', () => attachInput.click());
    attachInput.addEventListener('change', async () => {
      const file = attachInput.files[0];
      attachInput.value = '';
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      fd.append('device', deviceId);
      attachBtn.disabled = true;
      attachBtn.textContent = '…';
      try {
        const res = await fetch(uploadUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken() },
          credentials: 'same-origin',
          body: fd,
        });
        const data = await res.json();
        if (data.status) {
          pendingUpload = { url: data.url, filename: data.filename };
          Toast.ok(`Attached: ${data.filename}`);
        } else {
          Toast.err(data.reason || 'Upload failed.');
        }
      } catch (err) {
        Toast.err('Upload failed.');
      }
      attachBtn.disabled = false;
      attachBtn.textContent = '+';
    });
  }

  const composer = document.getElementById('chat-composer');
  if (composer) {
    composer.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = composer.querySelector('[name=message]');
      const text = input.value.trim();
      const upload = pendingUpload;
      if (!text && !upload) return;
      if (!token) { Toast.err('No connected device to send from.'); return; }

      input.value = '';
      pendingUpload = null;
      addBubble({
        id: 'tmp-' + Date.now(), direction: 'out', body: text, at: new Date().toISOString(),
        status: 'sending', attachment_url: upload ? upload.url : '', filename: upload ? upload.filename : '',
      });
      scrollDown();

      const body = { target: contact, message: text, preview: 'true' };
      if (upload) { body.url = upload.url; body.filename = upload.filename; }
      const data = await apiPost('/send', body, token);
      if (!data.status) {
        Toast.err(data.reason || 'Send failed.');
        input.value = text;
      }
    });
  }

  const syncBtn = document.getElementById('chat-sync-btn');
  if (syncBtn && syncUrl) {
    syncBtn.addEventListener('click', async () => {
      if (!deviceId) { Toast.err('No connected device to sync.'); return; }
      syncBtn.disabled = true;
      syncBtn.textContent = '…';
      try {
        const fd = new FormData();
        fd.append('device', deviceId);
        const res = await fetch(syncUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken() },
          credentials: 'same-origin',
          body: fd,
        });
        const data = await res.json();
        if (data.status) {
          Toast.ok(data.chats ? `Syncing history for ${data.chats} chat(s)…` : 'No history to sync.');
        } else {
          Toast.err(data.reason || 'Sync failed.');
        }
      } catch (err) {
        Toast.err('Sync failed.');
      }
      syncBtn.disabled = false;
      syncBtn.textContent = '⟳';
    });
  }

  const searchInput = document.getElementById('chat-search');
  if (searchInput && listRows) {
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.trim().toLowerCase();
      listRows.querySelectorAll('.chat-row').forEach(row => {
        const hay = (row.dataset.search || '').toLowerCase();
        row.style.display = !q || hay.includes(q) ? '' : 'none';
      });
    });
  }

  if (searchInput) {
    contactSearch(searchInput, (c) => {
      if (c.whatsapp) location.href = `/app/whatsapp/chats/${c.whatsapp}/`;
    });
  }

  if (listRows) {
    listRows.addEventListener('click', (e) => {
      const row = e.target.closest('.chat-row');
      if (row && row.href) { e.preventDefault(); location.href = row.href; }
    });
  }

  setInterval(async () => {
    const qs = new URLSearchParams();
    if (contact) qs.set('contact', contact);
    if (lastAt) qs.set('after', lastAt);
    if (deviceFilter) qs.set('device', deviceFilter);
    if (showAll) qs.set('all', '1');
    let data;
    try {
      data = await (await fetch(`${feedUrl}?${qs}`)).json();
    } catch (err) { return; }

    (data.messages || []).forEach(m => {
      const tmp = thread && thread.querySelector('[data-id^="tmp-"]');
      if (tmp && m.direction === 'out') tmp.remove();
      addBubble(m);
      if (m.at) lastAt = m.at;
    });
    if ((data.messages || []).length) scrollDown();

    if (listRows && data.chats) {
      const q = searchInput ? searchInput.value.trim().toLowerCase() : '';
      listRows.innerHTML = data.chats.map(c => {
        const label = c.name || c.contact;
        const hidden = q && !label.toLowerCase().includes(q) ? ' style="display:none"' : '';
        return `<a class="chat-row${c.contact === contact ? ' active' : ''}" href="${c.url}" data-contact="${c.contact}" data-search="${esc(label)}"${hidden}>
          <div class="msg-avatar">${esc(label.slice(0, 1).toUpperCase())}</div>
          <div class="chat-row-body">
            <div class="chat-row-top">
              <span class="chat-row-name">${esc(label)}</span>
              <span class="chat-row-time">${c.last_at ? fmt(c.last_at) : ''}</span>
            </div>
            <div class="chat-row-preview">${c.last_direction === 'out' ? 'You: ' : ''}${esc(c.last_body || '')}</div>
          </div></a>`;
      }).join('');
    }
  }, 5000);
}
