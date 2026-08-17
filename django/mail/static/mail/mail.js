/* ============================================================
   Mail section — mailbox management, connect/sync, compose.
   Depends on Toast/apiPost from core/core.js (loaded first).
   ============================================================ */

'use strict';

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
