/* ============================================================
   WhatsApp section — device connect/QR, send, message actions.
   Depends on Toast/apiPost from core/core.js (loaded first).
   ============================================================ */

'use strict';

// ── QR / connect modal ────────────────────────────────────────
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
    const rawQR = data.qr || data.url;  // worker returns bare base64 in 'url'
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
    // Poll device status until connected
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

// Wire up Connect buttons
document.querySelectorAll('[data-action=connect]').forEach(btn => {
  btn.addEventListener('click', () => {
    const { deviceId, token, phone } = btn.dataset;
    connectDevice(deviceId, token, phone);
  });
});

// ── disconnect device ─────────────────────────────────────────
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

// ── add device form ───────────────────────────────────────────
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

// ── send message form ─────────────────────────────────────────
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

  // Template fill
  document.querySelectorAll('[data-tpl]').forEach(btn => {
    btn.addEventListener('click', () => {
      const ta = sendForm.querySelector('[name=message]');
      ta.value = btn.dataset.tpl;
      ta.focus();
    });
  });
}

// ── delete message ────────────────────────────────────────────
document.querySelectorAll('[data-action=delete-msg]').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!confirm('Cancel this message?')) return;
    const { token, msgId } = btn.dataset;
    const data = await apiPost('/delete-message', { id: msgId }, token);
    if (data.status) {
      Toast.ok('Message cancelled.');
      btn.closest('tr')?.remove();
    } else {
      Toast.err(data.reason || 'Failed.');
    }
  });
});

// ── delete device ─────────────────────────────────────────────
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

// ── reschedule message ────────────────────────────────────────
document.querySelectorAll('[data-action=reschedule-msg]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const ts = prompt('New schedule (Unix timestamp in seconds):');
    if (!ts || isNaN(ts)) return;
    const { token, msgId } = btn.dataset;
    const data = await apiPost('/reschedule', { id: msgId, schedule: ts }, token);
    if (data.status) { Toast.ok('Rescheduled.'); }
    else { Toast.err(data.reason || 'Failed.'); }
  });
});

// ── close modal on backdrop click ────────────────────────────
if (qrModal) {
  qrModal.addEventListener('click', (e) => {
    if (e.target === qrModal) closeQrModal();
  });
}
