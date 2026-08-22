'use strict';

require('dotenv').config();
const express = require('express');
const cors = require('cors');

const {
  startSession,
  restoreAllSessions,
  sendMessage,
  validateNumbers,
  disconnectSession,
  getPendingQR,
  requestPairingCode,
  sendTyping,
  syncHistory,
  getActiveSessions,
  retryQueue,
} = require('./sessionManager');

const app = express();
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(cors({ origin: process.env.DJANGO_BASE_URL || 'http://localhost:8000', credentials: true }));

const PORT = process.env.WORKER_PORT || 3000;

function authMiddleware(req, res, next) {
  const auth = req.headers.authorization || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : auth;
  if (!token) {
    return res.status(401).json({ status: false, reason: 'no token provided' });
  }
  req.token = token;
  next();
}

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'wa-gateway-worker',
    activeSessions: getActiveSessions().length,
  });
});

app.use(authMiddleware);

app.post('/qr', async (req, res) => {
  const { deviceId, phoneNumber, type, whatsapp } = req.body;

  if (!deviceId || !phoneNumber) {
    return res.json({ status: false, reason: 'deviceId and phoneNumber required' });
  }

  try {
    await startSession(deviceId, phoneNumber);

    if (type === 'code') {
      let attempts = 0;
      let qr = getPendingQR(deviceId);
      while (!qr && attempts < 20) {
        await new Promise(resolve => setTimeout(resolve, 500));
        qr = getPendingQR(deviceId);
        attempts++;
      }

      if (!qr) {
        return res.json({ status: false, reason: 'session not ready for pairing code' });
      }

      try {
        const code = await requestPairingCode(deviceId, whatsapp || phoneNumber);
        return res.json({ status: true, code });
      } catch (e) {
        return res.json({ status: false, reason: 'pairing code failed: ' + e.message });
      }
    }

    let attempts = 0;
    let qr = getPendingQR(deviceId);
    while (!qr && attempts < 20) {
      await new Promise(resolve => setTimeout(resolve, 500));
      qr = getPendingQR(deviceId);
      attempts++;
    }

    if (qr) {
      const base64 = qr.split(',')[1];
      return res.json({ status: true, url: base64 });
    }

    return res.json({ status: false, reason: 'QR not generated, device may already be connected' });

  } catch (e) {
    console.error('QR error:', e);
    return res.json({ status: false, reason: e.message });
  }
});

app.post('/enqueue-send', async (req, res) => {
  const {
    deviceId, jid, messageId, message, url, filename,
    typing, delay_ms, schedule, followup, inboxid, preview, phoneNumber,
  } = req.body;

  if (!deviceId || !jid) {
    return res.json({ status: false, reason: 'deviceId and jid required' });
  }

  if (phoneNumber && !getActiveSessions().find(s => s.deviceId === deviceId)) {
    try { await startSession(deviceId, phoneNumber); } catch (e) { }
  }

  if (!getActiveSessions().find(s => s.deviceId === deviceId)) {
    return res.json({ status: false, reason: 'Device not connected. Run connect_whatsapp.sh to link your WhatsApp.' });
  }

  const scheduleMs = schedule && schedule > 0
    ? (schedule * 1000) - Date.now()
    : 0;

  const effectiveDelay = Math.max(scheduleMs, delay_ms || 0) + (followup ? followup * 1000 : 0);

  const deviceToken = req.token;
  const DJANGO_WEBHOOK_URL = process.env.DJANGO_WEBHOOK_URL || 'http://localhost:8000/webhook/incoming';
  const axios = require('axios');

  const doSend = async () => {
    const result = await sendMessage(deviceId, jid, { message, url, filename, typing, delay_ms: 0, preview });
    console.log(`[SEND] ${deviceId} -> ${jid}: OK`);
    if (result.id && messageId) {
      await axios.post(DJANGO_WEBHOOK_URL, {
        event: 'message_whatsapp_id', deviceId, id: messageId, whatsappId: result.id,
      }, { headers: { Authorization: deviceToken } }).catch(() => {});
      retryQueue.set(result.id, { deviceId, jid, options: { message, url, filename, typing, delay_ms: 0, preview }, messageId, retryCount: 0 });
    }
    return result;
  };

  const reportFailure = async (reason) => {
    console.error(`[SEND ERROR] ${deviceId} -> ${jid}:`, reason);
    await axios.post(DJANGO_WEBHOOK_URL, {
      event: 'message_status', deviceId, id: messageId, status: 'failed', state: 'failed', reason,
    }, { headers: { Authorization: deviceToken } }).catch(() => {});
  };

  if (effectiveDelay === 0) {
    try {
      const result = await doSend();
      return res.json({ status: true, id: result.id });
    } catch (e) {
      await reportFailure(e.message);
      return res.json({ status: false, reason: e.message });
    }
  }

  setTimeout(async () => {
    try { await doSend(); } catch (e) { await reportFailure(e.message); }
  }, effectiveDelay);

  return res.json({ status: true, id: messageId, queued: true });
});

app.post('/validate', async (req, res) => {
  const { deviceId, numbers } = req.body;

  if (!deviceId || !numbers || !Array.isArray(numbers)) {
    return res.json({ status: false, reason: 'deviceId and numbers[] required' });
  }

  try {
    const result = await validateNumbers(deviceId, numbers);
    return res.json(result);
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

app.post('/sync-history', async (req, res) => {
  const { deviceId, anchors } = req.body;
  if (!deviceId || !Array.isArray(anchors)) {
    return res.json({ status: false, reason: 'deviceId and anchors[] required' });
  }
  try {
    syncHistory(deviceId, anchors).catch((e) => {
      console.error(`[SYNC-HISTORY ERROR] ${deviceId}:`, e.message);
    });
    return res.json({ status: true, requested: anchors.length });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

app.post('/disconnect', async (req, res) => {
  const { deviceId } = req.body;
  if (!deviceId) {
    return res.json({ status: false, reason: 'deviceId required' });
  }
  try {
    await disconnectSession(deviceId);
    return res.json({ status: true, reason: 'device disconnected' });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

app.post('/typing', async (req, res) => {
  const { deviceId, jid, duration } = req.body;
  if (!deviceId || !jid) {
    return res.json({ status: false, reason: 'deviceId and jid required' });
  }
  try {
    await sendTyping(deviceId, jid, duration || 1);
    return res.json({ status: true });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

app.post('/delete-message', (req, res) => {
  const { deviceId, messageId } = req.body;
  return res.json({ status: true, reason: 'delete requested (may not apply if already sent)' });
});

app.post('/reschedule', (req, res) => {
  const { deviceId, messageId, schedule } = req.body;
  return res.json({ status: true, reason: 'reschedule requested' });
});

app.get('/sessions', (req, res) => {
  res.json({ status: true, sessions: getActiveSessions() });
});

app.listen(PORT, () => {
  console.log('========================================');
  console.log('  Messaging Platform — WhatsApp Worker (Baileys)');
  console.log('  Listening on port ' + PORT);
  console.log('  Django webhook: ' + (process.env.DJANGO_WEBHOOK_URL || 'http://localhost:8000/webhook/incoming'));
  console.log('========================================');
  restoreAllSessions().catch(e => console.error('Session restore error:', e));
});

process.on('SIGINT', () => {
  console.log('\nShutting down worker...');
  process.exit(0);
});
process.on('SIGTERM', () => {
  console.log('\nShutting down worker...');
  process.exit(0);
});
