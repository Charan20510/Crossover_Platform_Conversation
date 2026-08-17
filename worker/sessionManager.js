'use strict';

/**
 * Session Manager
 *
 * Manages WhatsApp WebSocket sessions using the Baileys library.
 * Each "device" in the Django DB maps to one Baileys WASocket instance
 * here. The Django backend talks to this worker over HTTP.
 *
 * Core responsibilities:
 *   - Start a session (generate QR / pairing code)
 *   - Persist auth credentials (so sessions survive restarts)
 *   - Send messages via WhatsApp's multi-device WebSocket
 *   - Receive inbound messages and forward to Django webhook
 *   - Report message delivery status back to Django
 */

const {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
} = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const QRCode = require('qrcode');
const P = require('pino');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

// ---- Config ----
const DJANGO_WEBHOOK_URL = process.env.DJANGO_WEBHOOK_URL || 'http://localhost:8000/webhook/incoming';

// ---- Session store ----
// Map<deviceId, { sock, phoneNumber, deviceId }>
const sessions = new Map();

// Pending QR codes (deviceId -> base64 data URL)
const pendingQRs = new Map();

// ---- 463 retry queue ----
// whatsappMsgId → { deviceId, jid, options, messageId, retryCount }
const retryQueue = new Map();

async function scheduleRetry(whatsappMsgId) {
  const entry = retryQueue.get(whatsappMsgId);
  if (!entry) return;
  if (entry.retryCount >= 3) {
    retryQueue.delete(whatsappMsgId);
    logger.warn({ whatsappMsgId, jid: entry.jid }, '463 retry exhausted — marking failed');
    await notifyDjango(entry.deviceId, {
      event: 'message_status_by_uuid', deviceId: entry.deviceId,
      id: entry.messageId, status: 'failed', state: 'failed',
    });
    return;
  }
  entry.retryCount++;
  const delayMs = 30 * 60 * 1000; // 30 minutes
  logger.info({ whatsappMsgId, retryCount: entry.retryCount, jid: entry.jid, delayMs }, '463 ack — scheduling retry');
  setTimeout(async () => {
    try {
      const result = await sendMessage(entry.deviceId, entry.jid, entry.options);
      retryQueue.delete(whatsappMsgId);
      await notifyDjango(entry.deviceId, { event: 'message_whatsapp_id', deviceId: entry.deviceId, id: entry.messageId, whatsappId: result.id });
      await notifyDjango(entry.deviceId, { event: 'message_status_by_uuid', deviceId: entry.deviceId, id: entry.messageId, status: 'sent', state: 'sent' });
      logger.info({ jid: entry.jid, attempt: entry.retryCount }, '463 retry succeeded');
    } catch (e) {
      logger.warn({ jid: entry.jid, attempt: entry.retryCount, err: e.message }, '463 retry failed again');
      scheduleRetry(whatsappMsgId);
    }
  }, delayMs);
}

// ---- Auth directory ----
const AUTH_DIR = path.join(__dirname, 'auth_states');
if (!fs.existsSync(AUTH_DIR)) {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
}

// ---- Logger ----
const logger = P({ level: process.env.LOG_LEVEL || 'info' });

/**
 * Start a new WhatsApp session for a device.
 * @param {string} deviceId - UUID of the device in Django DB
 * @param {string} phoneNumber - phone number (international format)
 */
async function startSession(deviceId, phoneNumber) {
  // If session already exists and is active, return it
  if (sessions.has(deviceId)) {
    const existing = sessions.get(deviceId);
    if (existing.sock && (existing.sock.user || pendingQRs.has(deviceId))) {
      return existing;
    }
  }

  // Use multi-file auth state (persists in ./auth_states/<deviceId>/)
  const authDir = path.join(AUTH_DIR, deviceId);
  const { state, saveCreds } = await useMultiFileAuthState(authDir);

  // Use the latest Baileys version
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    auth: state,
    version,
    printQRInTerminal: false,
    browser: Browsers.ubuntu('Chrome'),
    logger: logger.child({ class: 'wa', deviceId }),
    generateHighQualityLinkPreview: true,
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });

  const sessionData = { sock, phoneNumber, deviceId, connectedAt: null };
  sessions.set(deviceId, sessionData);
  fs.writeFileSync(path.join(authDir, 'device.json'), JSON.stringify({ phoneNumber }));

  // ---- Event: connection update (QR, open, close) ----
  sock.ev.on('connection.update', async (update) => {
    const { connection, qr, lastDisconnect } = update;

    if (qr) {
      // Generate QR as base64 data URL (matches Fonnte's API)
      const dataUrl = await QRCode.toDataURL(qr, { width: 256 });
      pendingQRs.set(deviceId, dataUrl);
      logger.info({ deviceId }, 'QR generated, waiting for scan');
    }

    if (connection === 'open') {
      pendingQRs.delete(deviceId);
      sessionData.connectedAt = Date.now();
      logger.info({ deviceId, phoneNumber }, 'WhatsApp connection opened');
      // Briefly mark available then unavailable — mimics natural device wake-up,
      // helps WA servers register this as an active linked device faster.
      setTimeout(async () => {
        try {
          await sock.sendPresenceUpdate('available');
          await new Promise(r => setTimeout(r, 2000));
          await sock.sendPresenceUpdate('unavailable');
        } catch (_) {}
      }, 1000);
      // Notify Django that device is connected
      await notifyDjango(deviceId, {
        event: 'device_status',
        deviceId,
        status: 'connect',
        timestamp: Date.now(),
      });
    }

    if (connection === 'close') {
      pendingQRs.delete(deviceId);
      const statusCode = (lastDisconnect && lastDisconnect.error instanceof Boom)
        ? lastDisconnect.error.output && lastDisconnect.error.output.statusCode
        : undefined;

      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      logger.warn({ deviceId, statusCode, shouldReconnect }, 'Connection closed');

      if (shouldReconnect) {
        // Reconnect after 3 seconds
        setTimeout(() => startSession(deviceId, phoneNumber), 3000);
      } else {
        // Logged out — clean up auth state
        logger.error({ deviceId }, 'Device logged out, cleaning up');
        sessions.delete(deviceId);
        pendingQRs.delete(deviceId);
        try {
          fs.rmSync(authDir, { recursive: true, force: true });
        } catch (e) { /* ignore */ }
      }

      // Notify Django
      await notifyDjango(deviceId, {
        event: 'device_status',
        deviceId,
        status: 'disconnect',
        reason: (lastDisconnect && lastDisconnect.error && lastDisconnect.error.message) || 'unknown',
        timestamp: Date.now(),
      });
    }
  });

  // ---- Event: save credentials (persist session) ----
  sock.ev.on('creds.update', saveCreds);

  // ---- Event: incoming messages ----
  sock.ev.on('messages.upsert', async (event) => {
    if (event.type !== 'notify') return;

    for (const msg of event.messages) {
      // Skip own messages
      if (msg.key.fromMe) continue;

      const sender = msg.key.remoteJid || '';
      const messageText = extractMessageText(msg.message);
      const pushName = msg.pushName || '';
      const timestamp = msg.messageTimestamp || Date.now();
      const inboxId = msg.key.id || '';

      // Extract location if present
      let location = null;
      if (msg.message && msg.message.locationMessage) {
        const lat = msg.message.locationMessage.degreesLatitude;
        const lng = msg.message.locationMessage.degreesLongitude;
        location = lat + ',' + lng;
      }

      // Extract attachment info if present
      let attachmentUrl = null;
      if (msg.message && (msg.message.imageMessage || msg.message.videoMessage ||
          msg.message.audioMessage || msg.message.documentMessage)) {
        // In production: download media from WhatsApp, store to S3/MinIO
        attachmentUrl = 'media_pending_download';
      }

      logger.info({ deviceId, sender, preview: (messageText || '').slice(0, 40) }, 'Incoming message');

      // Forward to Django webhook
      await notifyDjango(deviceId, {
        event: 'incoming_message',
        deviceId,
        sender,
        message: messageText,
        name: pushName,
        location,
        url: attachmentUrl,
        inboxid: inboxId,
        timestamp: typeof timestamp === 'number' ? timestamp : Date.now(),
      });
    }
  });

  // ---- Event: message status updates (sent/delivered/read) ----
  sock.ev.on('messages.update', async (updates) => {
    for (const update of updates) {
      if (!update.key || !update.update) continue;

      const messageId = update.key.id;
      const status = mapWhatsAppStatus(update.update.status);

      if (status === 'failed') {
        // Route through retry queue — if no entry, falls through to direct Django notification
        if (retryQueue.has(messageId)) {
          await scheduleRetry(messageId);
          continue;
        }
      }

      if (status) {
        logger.debug({ deviceId, messageId, status }, 'Message status update');
        await notifyDjango(deviceId, {
          event: 'message_status',
          deviceId,
          id: messageId,
          status,
          state: status,
        });
      }
    }
  });

  // ---- Event: server-side receipt failures (e.g. error 463) ----
  sock.ev.on('message-receipt.update', async (updates) => {
    for (const { key, receipt } of updates) {
      // A receipt without a receiptTimestamp means the server rejected delivery
      if (!receipt || receipt.receiptTimestamp) continue;
      logger.warn({ deviceId, messageId: key.id }, 'Message receipt rejected by server — trying retry queue');
      await scheduleRetry(key.id);
    }
  });

  return sessionData;
}

/**
 * Extract text from a WhatsApp message object.
 */
function extractMessageText(message) {
  if (!message) return '';
  if (message.conversation) return message.conversation;
  if (message.extendedTextMessage && message.extendedTextMessage.text) return message.extendedTextMessage.text;
  if (message.imageMessage && message.imageMessage.caption) return message.imageMessage.caption;
  if (message.videoMessage && message.videoMessage.caption) return message.videoMessage.caption;
  return '';
}

/**
 * Map WhatsApp status codes to Fonnte-style status strings.
 */
function mapWhatsAppStatus(status) {
  switch (status) {
    case 0: return 'failed';    // ERROR
    case 1: return null;        // PENDING
    case 2: return 'sent';      // SERVER_ACK
    case 3: return 'delivered'; // DELIVERY_ACK
    case 4: return 'read';      // READ
    case 5: return 'read';      // PLAYED (voice)
    default: return null;
  }
}

/**
 * Send a message through a specific device's WhatsApp session.
 * @param {string} deviceId
 * @param {string} jid - recipient JID (xxx@s.whatsapp.net)
 * @param {object} options - { message, url, typing, delay_ms, filename, ... }
 * @returns {object} { status, id }
 */
async function sendMessage(deviceId, jid, options) {
  const session = sessions.get(deviceId);
  if (!session || !session.sock || !session.sock.user) {
    throw new Error('Device not connected or still authenticating — wait a moment and retry');
  }

  const sock = session.sock;
  const messageText = options.message || '';
  const attachmentUrl = options.url || '';
  const typing = options.typing || false;

  // Validate recipient is on WhatsApp (skip for group JIDs)
  if (!jid.endsWith('@g.us')) {
    try {
      const [exists] = await sock.onWhatsApp(jid);
      if (!exists || !exists.exists) {
        throw new Error(`Number ${jid.split('@')[0]} is not registered on WhatsApp`);
      }
    } catch (e) {
      if (e.message.includes('not registered')) throw e;
      // onWhatsApp lookup failed (network) — proceed anyway
      logger.warn({ jid, err: e.message }, 'onWhatsApp lookup failed, proceeding with send');
    }
  }

  // Subscribe to contact presence — signals WA servers we have a chat relationship
  // with this JID, reducing the "new device sending cold" signal that triggers 463.
  if (!jid.endsWith('@g.us')) {
    try { await sock.presenceSubscribe(jid); } catch (_) {}
    await new Promise(r => setTimeout(r, 500));
  }

  // Simulate typing if requested
  if (typing) {
    await sock.sendPresenceUpdate('composing', jid);
    await new Promise(resolve => setTimeout(resolve, 1500));
    await sock.sendPresenceUpdate('paused', jid);
  }

  // Apply delay if specified (anti-ban random delay)
  if (options.delay_ms && options.delay_ms > 0) {
    await new Promise(resolve => setTimeout(resolve, options.delay_ms));
  }

  // Warm-up: wait until 30s have passed since connection opened (new device trust)
  // ponytail: 30s is a rough heuristic; tune down once device has aged past 48h
  const warmupMs = 30000 - (Date.now() - (session.connectedAt || 0));
  if (warmupMs > 0) {
    logger.info({ deviceId, warmupMs }, 'Warm-up delay before send');
    await new Promise(r => setTimeout(r, warmupMs));
  }

  function mapSendError(e) {
    if (e.output?.statusCode === 463 || e.message?.includes('463')) {
      throw new Error('Recipient not on WhatsApp or has blocked messages (error 463)');
    }
    throw e;
  }

  let result;

  if (attachmentUrl) {
    const isImage = attachmentUrl.match(/\.(jpg|jpeg|png|gif|webp)$/i);
    const isVideo = attachmentUrl.match(/\.(mp4|webm|mov|avi)$/i);
    const isAudio = attachmentUrl.match(/\.(mp3|ogg|wav|m4a)$/i);

    try {
      if (isImage) {
        result = await sock.sendMessage(jid, { image: { url: attachmentUrl }, caption: messageText });
      } else if (isVideo) {
        result = await sock.sendMessage(jid, { video: { url: attachmentUrl }, caption: messageText });
      } else if (isAudio) {
        result = await sock.sendMessage(jid, { audio: { url: attachmentUrl }, mimetype: 'audio/mpeg' });
      } else {
        result = await sock.sendMessage(jid, {
          document: { url: attachmentUrl },
          fileName: options.filename || 'file',
          caption: messageText,
        });
      }
    } catch (e) { mapSendError(e); }
  } else {
    try {
      result = await sock.sendMessage(jid, { text: messageText });
    } catch (e) { mapSendError(e); }
  }

  return {
    status: true,
    id: (result && result.key && result.key.id) || uuidv4(),
  };
}

/**
 * Validate if numbers are registered on WhatsApp.
 * @param {string} deviceId
 * @param {string[]} numbers - array of phone numbers (international format)
 * @returns {object} { status, registered: [], not_registered: [] }
 */
async function validateNumbers(deviceId, numbers) {
  const session = sessions.get(deviceId);
  if (!session || !session.sock) {
    throw new Error('Device not connected');
  }

  const sock = session.sock;
  const registered = [];
  const notRegistered = [];

  for (const number of numbers) {
    const jid = number + '@s.whatsapp.net';
    try {
      const exists = await sock.onWhatsApp(jid);
      if (exists && exists.length > 0 && exists[0].exists) {
        registered.push(number);
      } else {
        notRegistered.push(number);
      }
    } catch (e) {
      notRegistered.push(number);
    }
  }

  return { status: true, registered, not_registered: notRegistered };
}

/**
 * Disconnect a device session and clean up.
 */
async function disconnectSession(deviceId) {
  const session = sessions.get(deviceId);
  if (session && session.sock) {
    try { await session.sock.logout(); } catch (e) { /* ignore */ }
    sessions.delete(deviceId);
    pendingQRs.delete(deviceId);

    // Clean up auth files
    const authDir = path.join(AUTH_DIR, deviceId);
    try { fs.rmSync(authDir, { recursive: true, force: true }); } catch (e) { /* ignore */ }
  }
}

/**
 * Get the pending QR code for a device (base64 PNG data URL).
 */
function getPendingQR(deviceId) {
  return pendingQRs.get(deviceId);
}

/**
 * Request a pairing code for a device (alternative to QR).
 */
async function requestPairingCode(deviceId, phoneNumber) {
  const session = sessions.get(deviceId);
  if (!session || !session.sock) {
    throw new Error('Session not started');
  }
  const code = await session.sock.requestPairingCode(phoneNumber);
  return code;
}

/**
 * Send typing indicator to a chat.
 */
async function sendTyping(deviceId, jid, duration) {
  const session = sessions.get(deviceId);
  if (!session || !session.sock) {
    throw new Error('Device not connected');
  }
  const sock = session.sock;
  await sock.sendPresenceUpdate('composing', jid);
  if (duration > 0) {
    await new Promise(resolve => setTimeout(resolve, duration * 1000));
  }
  await sock.sendPresenceUpdate('paused', jid);
}

/**
 * Notify Django of an event (incoming message, status, device status).
 */
async function notifyDjango(deviceId, payload) {
  try {
    await axios.post(DJANGO_WEBHOOK_URL, payload, { timeout: 10000 });
  } catch (e) {
    logger.error({ deviceId, error: e.message }, 'Failed to notify Django');
  }
}

/**
 * Get all active session IDs.
 */
function getActiveSessions() {
  const active = [];
  for (const [deviceId, session] of sessions) {
    if (session.sock && session.sock.user) {
      active.push({ deviceId, phoneNumber: session.phoneNumber, connected: true });
    }
  }
  return active;
}

async function restoreAllSessions() {
  if (!fs.existsSync(AUTH_DIR)) return;
  const dirs = fs.readdirSync(AUTH_DIR);
  for (const deviceId of dirs) {
    const metaPath = path.join(AUTH_DIR, deviceId, 'device.json');
    if (!fs.existsSync(metaPath)) continue;
    try {
      const { phoneNumber } = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
      logger.info({ deviceId }, 'Restoring session on startup');
      await startSession(deviceId, phoneNumber);
    } catch (e) {
      logger.warn({ deviceId, err: e.message }, 'Failed to restore session on startup');
    }
  }
}

module.exports = {
  startSession,
  restoreAllSessions,
  sendMessage,
  validateNumbers,
  disconnectSession,
  getPendingQR,
  requestPairingCode,
  sendTyping,
  getActiveSessions,
  sessions,
  retryQueue,
};
