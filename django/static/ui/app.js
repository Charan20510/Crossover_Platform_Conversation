/* ============================================================
   WhatsApp Gateway UI — client-side helpers
   ============================================================ */

'use strict';

// ── toast ────────────────────────────────────────────────────
const Toast = (() => {
  let container = null;
  function _ensure() {
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }
  }
  function show(msg, type = 'info', duration = 3500) {
    _ensure();
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(40px)';
      el.style.transition = 'opacity .3s, transform .3s';
      setTimeout(() => el.remove(), 320);
    }, duration);
  }
  return { show, ok: (m) => show(m, 'ok'), err: (m) => show(m, 'err', 4500) };
})();

// ── fetch wrapper (attaches device/account token) ────────────
async function apiPost(url, body, token) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': token } : {}),
    },
    body: JSON.stringify(body),
  });
  return res.json();
}

// ── copy to clipboard ────────────────────────────────────────
function copyText(text) {
  navigator.clipboard.writeText(text).then(() => Toast.ok('Copied!'));
}
document.querySelectorAll('.token-box').forEach(el => {
  el.title = 'Click to copy';
  el.addEventListener('click', () => copyText(el.dataset.full || el.textContent.trim()));
});

// ── count-up animation ───────────────────────────────────────
function countUp(el, target, duration = 800) {
  const start = performance.now();
  const from = parseInt(el.textContent, 10) || 0;
  function step(now) {
    const p = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(from + (target - from) * ease);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
document.querySelectorAll('.stat-value[data-count]').forEach(el => {
  countUp(el, parseInt(el.dataset.count, 10));
});

// ── notification bell polling ─────────────────────────────────
const bell = document.getElementById('bell-btn');
const bellBadge = document.getElementById('bell-badge');
let lastCount = 0;

async function pollNotifications() {
  try {
    const data = await fetch('/app/notifications/').then(r => r.json());
    const count = data.count || 0;
    if (bellBadge) {
      if (count > 0) {
        bellBadge.textContent = count > 99 ? '99+' : count;
        bellBadge.classList.add('visible');
      } else {
        bellBadge.classList.remove('visible');
      }
    }
    if (count > lastCount && lastCount !== null) {
      const newest = (data.latest || [])[0];
      if (newest && bell) {
        bell.classList.add('ringing');
        setTimeout(() => bell.classList.remove('ringing'), 600);
        const who = newest.name || newest.sender || 'someone';
        const preview = (newest.message || '').slice(0, 60);
        Toast.show(`💬 New message from <b>${who}</b>: ${preview}`, 'info', 5000);
      }
    }
    lastCount = count;
  } catch (_) { /* silently fail */ }
}

if (bell) {
  pollNotifications();
  setInterval(pollNotifications, 10000);
}

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

// ── template insert into send form ───────────────────────────
// (already handled above via [data-tpl])

// ── close modal on backdrop click ────────────────────────────
if (qrModal) {
  qrModal.addEventListener('click', (e) => {
    if (e.target === qrModal) closeQrModal();
  });
}

// ── add mail account form ─────────────────────────────────────
const mailAccountForm = document.getElementById('mail-account-form');
if (mailAccountForm) {
  mailAccountForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const accountToken = mailAccountForm.dataset.accountToken;
    const fields = ['name', 'email_address', 'username', 'password', 'imap_host', 'imap_port', 'smtp_host', 'smtp_port'];
    const body = {};
    fields.forEach(f => { body[f] = mailAccountForm.querySelector(`[name=${f}]`).value.trim(); });
    if (!body.name || !body.email_address || !body.password || !body.imap_host || !body.smtp_host) {
      Toast.err('Please fill in all required fields.');
      return;
    }

    const btn = mailAccountForm.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Adding…';

    const data = await apiPost('/mail/account', body, accountToken);
    btn.disabled = false;
    btn.textContent = 'Add Mail Account';

    if (data.status) {
      Toast.ok(`Mail account "${body.name}" added.`);
      setTimeout(() => location.reload(), 1200);
    } else {
      Toast.err(data.reason || 'Failed to add mail account.');
    }
  });
}

// ── connect mail account (test IMAP) ──────────────────────────
document.querySelectorAll('[data-action=mail-connect]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const { token } = btn.dataset;
    btn.disabled = true;
    const data = await apiPost('/mail/connect', {}, token);
    btn.disabled = false;
    if (data.status) {
      Toast.ok('Mail account connected.');
      setTimeout(() => location.reload(), 800);
    } else {
      Toast.err(data.reason || 'Connection failed.');
    }
  });
});

// ── sync mail account ─────────────────────────────────────────
document.querySelectorAll('[data-action=mail-sync]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const { token } = btn.dataset;
    btn.disabled = true;
    btn.textContent = 'Syncing…';
    const data = await apiPost('/mail/sync', {}, token);
    btn.disabled = false;
    btn.textContent = 'Sync';
    if (data.status) {
      Toast.ok(`Synced. ${data.new || 0} new email(s).`);
      setTimeout(() => location.reload(), 800);
    } else {
      Toast.err(data.reason || 'Sync failed.');
    }
  });
});

// ── delete mail account ───────────────────────────────────────
document.querySelectorAll('[data-action=delete-mail-account]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const { token, name } = btn.dataset;
    if (!confirm(`Delete mail account "${name}"? This removes it and its email history permanently.`)) return;
    btn.disabled = true;
    const data = await apiPost('/mail/delete-account', {}, token);
    if (data.status) {
      Toast.ok('Mail account deleted.');
      setTimeout(() => location.reload(), 800);
    } else {
      Toast.err(data.reason || 'Failed to delete.');
      btn.disabled = false;
    }
  });
});

// ── mail compose form ─────────────────────────────────────────
const mailComposeForm = document.getElementById('mail-compose-form');
if (mailComposeForm) {
  const acctSel = mailComposeForm.querySelector('[name=mail_account]');
  const resultBox = document.getElementById('mail-send-result');

  mailComposeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = acctSel.options[acctSel.selectedIndex]?.dataset.token || '';
    if (!token) { Toast.err('Select a connected mail account.'); return; }

    const body = {
      to:      mailComposeForm.querySelector('[name=to]').value.trim(),
      cc:      mailComposeForm.querySelector('[name=cc]').value.trim(),
      bcc:     mailComposeForm.querySelector('[name=bcc]').value.trim(),
      subject: mailComposeForm.querySelector('[name=subject]').value.trim(),
      text:    mailComposeForm.querySelector('[name=text]').value.trim(),
    };
    if (!body.to) { Toast.err('Recipient required.'); return; }

    const btn = mailComposeForm.querySelector('button[type=submit]');
    btn.disabled = true; btn.textContent = 'Sending…';
    const data = await apiPost('/mail/send', body, token);
    btn.disabled = false; btn.textContent = 'Send';

    if (data.status) {
      Toast.ok(`✓ Email sent to ${body.to}.`);
      if (resultBox) resultBox.innerHTML =
        `<div class="alert alert-success">Sent! ID: ${data.id || ''}</div>`;
    } else {
      Toast.err(data.reason || 'Send failed.');
      if (resultBox) resultBox.innerHTML =
        `<div class="alert alert-error">${data.reason || 'Failed'}</div>`;
    }
  });
}
