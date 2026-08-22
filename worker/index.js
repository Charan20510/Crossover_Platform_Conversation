'use strict';

/**
 * Messaging Platform — WhatsApp Worker — Express HTTP server
 *
 * This is the Node.js microservice that talks to WhatsApp via Baileys.
 * The Django backend calls this worker's HTTP endpoints to:
 *   - Start sessions / get QR codes
 *   - Enqueue messages for sending
 *   - Validate numbers
 *   - Disconnect devices
 *
 * The worker pushes inbound events (incoming messages, status updates,
 * device status changes) BACK to Django via the Django webhook endpoint.
 */

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
// CORS: only allow requests from Django (localhost) — not the open web
app.use(cors({ origin: process.env.DJANGO_BASE_URL || 'http://localhost:8000', credentials: true }));

const PORT = process.env.WORKER_PORT || 3000;

// Simple token auth (matches the device token from Django)
function authMiddleware(req, res, next) {
  const auth = req.headers.authorization || '';
  // Accept "TOKEN" or "Bearer TOKEN"
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : auth;
  if (!token) {
    return res.status(401).json({ status: false, reason: 'no token provided' });
  }
  // In production: validate token against Django DB or a shared cache
  // For now, we trust the token — Django has already validated it before calling us
  req.token = token;
  next();
}

// ============================================================
// HEALTH (public)
// ============================================================
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'wa-gateway-worker',
    activeSessions: getActiveSessions().length,
  });
});

// Apply auth to all routes below this line
app.use(authMiddleware);

// ============================================================
// START SESSION / GET QR
// ============================================================
app.post('/qr', async (req, res) => {
  const { deviceId, phoneNumber, type, whatsapp } = req.body;

  if (!deviceId || !phoneNumber) {
    return res.json({ status: false, reason: 'deviceId and phoneNumber required' });
  }

  try {
    // Start (or resume) the Baileys session
    await startSession(deviceId, phoneNumber);

    // If pairing code requested
    if (type === 'code') {
      // Wait for socket to reach QR-ready state before requesting pairing code
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

    // QR code — wait for it to be generated (poll up to 10 seconds)
    let attempts = 0;
    let qr = getPendingQR(deviceId);
    while (!qr && attempts < 20) {
      await new Promise(resolve => setTimeout(resolve, 500));
      qr = getPendingQR(deviceId);
      attempts++;
    }

    if (qr) {
      // Return base64 PNG (without the data:image/png;base64, prefix, like Fonnte)
      const base64 = qr.split(',')[1];
      return res.json({ status: true, url: base64 });
    }

    // If no QR, maybe already connected
    return res.json({ status: false, reason: 'QR not generated, device may already be connected' });

  } catch (e) {
    console.error('QR error:', e);
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// ENQUEUE SEND MESSAGE
// ============================================================
app.post('/enqueue-send', async (req, res) => {
  const {
    deviceId, jid, messageId, message, url, filename,
    typing, delay_ms, schedule, followup, inboxid, preview, phoneNumber,
  } = req.body;

  if (!deviceId || !jid) {
    return res.json({ status: false, reason: 'deviceId and jid required' });
  }

  // Auto-start session if not active (e.g. after server restart)
  if (phoneNumber && !getActiveSessions().find(s => s.deviceId === deviceId)) {
    try { await startSession(deviceId, phoneNumber); } catch (e) { /* will surface at send time */ }
  }

  // Reject immediately if session still not connected
  if (!getActiveSessions().find(s => s.deviceId === deviceId)) {
    return res.json({ status: false, reason: 'Device not connected. Run connect_whatsapp.sh to link your WhatsApp.' });
  }

  // If scheduled for the future, delay sending
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
      // Register in retry queue so 463 acks trigger automatic retry
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

  // Immediate send: await inline so the caller gets the real result
  if (effectiveDelay === 0) {
    try {
      const result = await doSend();
      return res.json({ status: true, id: result.id });
    } catch (e) {
      await reportFailure(e.message);
      return res.json({ status: false, reason: e.message });
    }
  }

  // Scheduled/delayed send: fire-and-forget, return queued acknowledgement
  setTimeout(async () => {
    try { await doSend(); } catch (e) { await reportFailure(e.message); }
  }, effectiveDelay);

  return res.json({ status: true, id: messageId, queued: true });
});

// ============================================================
// VALIDATE NUMBERS
// ============================================================
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

// ============================================================
// SYNC HISTORY (on-demand backfill for an already-linked device)
// ============================================================
app.post('/sync-history', async (req, res) => {
  const { deviceId, anchors } = req.body;
  if (!deviceId || !Array.isArray(anchors)) {
    return res.json({ status: false, reason: 'deviceId and anchors[] required' });
  }
  try {
    // Fire-and-forget: results land in Django via the messaging-history.set
    // handler / webhook, not in this response.
    syncHistory(deviceId, anchors).catch((e) => {
      console.error(`[SYNC-HISTORY ERROR] ${deviceId}:`, e.message);
    });
    return res.json({ status: true, requested: anchors.length });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// DISCONNECT
// ============================================================
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

// ============================================================
// TYPING INDICATOR
// ============================================================
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

// ============================================================
// DELETE MESSAGE (cancel — best effort, only works if not yet sent)
// ============================================================
app.post('/delete-message', (req, res) => {
  // Messages that haven't been sent yet are in the setTimeout queue.
  // In production, use a proper job queue (BullMQ) that supports cancellation.
  // For this MVP, we acknowledge the request — the message may or may not be cancelled.
  const { deviceId, messageId } = req.body;
  return res.json({ status: true, reason: 'delete requested (may not apply if already sent)' });
});

// ============================================================
// RESCHEDULE
// ============================================================
app.post('/reschedule', (req, res) => {
  const { deviceId, messageId, schedule } = req.body;
  // In production with BullMQ: job.changeDelay(schedule * 1000 - Date.now())
  return res.json({ status: true, reason: 'reschedule requested' });
});

// ============================================================
// ACTIVE SESSIONS
// ============================================================
app.get('/sessions', (req, res) => {
  res.json({ status: true, sessions: getActiveSessions() });
});

// ============================================================
// START SERVER
// ============================================================
app.listen(PORT, () => {
  console.log('========================================');
  console.log('  Messaging Platform — WhatsApp Worker (Baileys)');
  console.log('  Listening on port ' + PORT);
  console.log('  Django webhook: ' + (process.env.DJANGO_WEBHOOK_URL || 'http://localhost:8000/webhook/incoming'));
  console.log('========================================');
  restoreAllSessions().catch(e => console.error('Session restore error:', e));
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down worker...');
  process.exit(0);
});
process.on('SIGTERM', () => {
  console.log('\nShutting down worker...');
  process.exit(0);
});
