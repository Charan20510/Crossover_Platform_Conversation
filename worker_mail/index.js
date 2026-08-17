'use strict';

/**
 * Mail Gateway Worker — Express HTTP server
 *
 * This Node.js microservice handles email operations using:
 *   - ImapFlow  → fetch emails, list folders (IMAP)
 *   - Nodemailer → send emails (SMTP)
 *
 * The Django backend calls this worker's HTTP endpoints to:
 *   - Connect / test IMAP connections
 *   - Send emails via SMTP
 *   - Fetch emails from folders
 *   - List IMAP folders
 *   - Search emails
 *
 * This is the "Baileys equivalent for email" — a thin protocol layer
 * that Django talks to over HTTP, exactly like the WhatsApp worker pattern.
 */

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { ImapFlow } = require('imapflow');
const { simpleParser } = require('mailparser');
const nodemailer = require('nodemailer');
const axios = require('axios');

const app = express();
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(cors({ origin: true, credentials: true }));

const PORT = process.env.WORKER_MAIL_PORT || 3002;
const DJANGO_WEBHOOK_URL = process.env.DJANGO_WEBHOOK_URL || 'http://localhost:8000/webhook/mail';

// Simple token auth (matches the mail account token from Django)
function authMiddleware(req, res, next) {
  const auth = req.headers.authorization || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : auth;
  if (!token) {
    return res.status(401).json({ status: false, reason: 'no token provided' });
  }
  req.token = token;
  next();
}

// ============================================================
// HEALTH (public)
// ============================================================
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'mail-gateway-worker' });
});

app.use(authMiddleware);

// ============================================================
// CONNECT / TEST IMAP CONNECTION
// ============================================================
app.post('/connect', async (req, res) => {
  const { accountId, imapHost, imapPort, imapSecure, username, password } = req.body;

  if (!imapHost || !username) {
    return res.json({ status: false, reason: 'imapHost and username required' });
  }

  try {
    const client = new ImapFlow({
      host: imapHost,
      port: imapPort || 993,
      secure: imapSecure !== false,
      auth: { user: username, pass: password },
      logger: false,
    });

    await client.connect();
    const mailbox = await client.mailboxOpen('INBOX');
    const status = await client.status('INBOX', { messages: true, unseen: true });

    await client.mailboxClose();
    await client.logout();

    // Notify Django of connection success
    try {
      await axios.post(DJANGO_WEBHOOK_URL, {
        event: 'account_status',
        accountId,
        status: 'connect',
      });
    } catch (_) {}

    return res.json({
      status: true,
      message: 'Connected successfully',
      inbox: { total: status.messages, unseen: status.unseen },
    });
  } catch (e) {
    // Notify Django of connection failure
    try {
      await axios.post(DJANGO_WEBHOOK_URL, {
        event: 'account_status',
        accountId,
        status: 'error',
        reason: e.message,
      });
    } catch (_) {}

    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// SEND EMAIL (SMTP via Nodemailer)
// ============================================================
app.post('/send', async (req, res) => {
  const {
    from, to, cc, bcc, subject, text, html, attachments,
    smtpHost, smtpPort, smtpSecure, username, password,
  } = req.body;

  if (!to || !smtpHost) {
    return res.json({ status: false, reason: 'to and smtpHost required' });
  }

  try {
    const transporter = nodemailer.createTransport({
      host: smtpHost,
      port: smtpPort || 587,
      secure: (smtpPort == 465) || smtpSecure === true,
      auth: { user: username, pass: password },
    });

    const mailOptions = {
      from: from,
      to: to,
      cc: cc || '',
      bcc: bcc || '',
      subject: subject || '(no subject)',
      text: text || '',
      html: html || '',
      attachments: attachments || [],
    };

    const info = await transporter.sendMail(mailOptions);

    return res.json({
      status: true,
      messageId: info.messageId,
      response: info.response,
    });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// FETCH EMAILS (IMAP via ImapFlow)
// ============================================================
app.post('/fetch', async (req, res) => {
  const {
    accountId, folder, limit, unseen, search,
    imapHost, imapPort, imapSecure, username, password,
  } = req.body;

  if (!imapHost || !username) {
    return res.json({ status: false, reason: 'imapHost and username required' });
  }

  let client;
  try {
    client = new ImapFlow({
      host: imapHost,
      port: imapPort || 993,
      secure: imapSecure !== false,
      auth: { user: username, pass: password },
      logger: false,
    });

    await client.connect();
    await client.mailboxOpen(folder || 'INBOX');

    // Build search criteria
    const searchCriteria = {};
    if (unseen) searchCriteria.seen = false;
    if (search) searchCriteria.subject = search;

    // Get message UIDs
    const uids = await client.search(searchCriteria, { uid: true });
    const fetchLimit = Math.min(limit || 50, 200);
    const uidsToFetch = uids.slice(-fetchLimit).reverse(); // most recent first

    const emails = [];

    for (const uid of uidsToFetch) {
      const msg = await client.fetchOne(uid, { source: true, envelope: true, flags: true, bodyStructure: true }, { uid: true });

      if (!msg) continue;

      const envelope = msg.envelope || {};
      const flags = msg.flags || new Set();
      const hasAttachments = msg.bodyStructure && msg.bodyStructure.childNodes
        ? msg.bodyStructure.childNodes.some(n => n.disposition === 'attachment')
        : false;

      let bodyText = '';
      let bodyHtml = '';

      // Parse the raw source for body content
      if (msg.source) {
        try {
          const raw = msg.source instanceof Buffer ? msg.source : Buffer.from(msg.source);
          const parsed = await simpleParser(raw);
          bodyText = parsed.text || '';
          bodyHtml = parsed.html || '';
        } catch (_) {
          // If parsing fails, skip body
        }
      }

      emails.push({
        uid,
        messageId: envelope.messageId || '',
        subject: envelope.subject || '(no subject)',
        from: envelope.from && envelope.from[0] ? `${envelope.from[0].address}` : '',
        fromName: envelope.from && envelope.from[0] ? envelope.from[0].name || '' : '',
        to: envelope.to ? envelope.to.map(a => a.address).join(', ') : '',
        date: envelope.date ? envelope.date.toISOString() : new Date().toISOString(),
        isRead: flags.has('\\Seen'),
        hasAttachments,
        attachmentCount: hasAttachments ? 1 : 0,
        text: bodyText.substring(0, 5000),
        html: bodyHtml.substring(0, 10000),
        size: msg.size || 0,
      });
    }

    await client.mailboxClose();
    await client.logout();

    // Notify Django of incoming emails (for real-time webhook)
    for (const em of emails) {
      if (!em.isRead) {
        try {
          await axios.post(DJANGO_WEBHOOK_URL, {
            event: 'incoming_email',
            accountId,
            messageId: em.messageId,
            subject: em.subject,
            from: em.from,
            to: em.to,
            text: em.text.substring(0, 1000),
            html: em.html.substring(0, 2000),
            hasAttachments: em.hasAttachments,
            attachmentCount: em.attachmentCount,
            folder: folder || 'INBOX',
          });
        } catch (_) {}
      }
    }

    return res.json({ status: true, count: emails.length, emails });
  } catch (e) {
    if (client) {
      try { await client.logout(); } catch (_) {}
    }
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// LIST IMAP FOLDERS
// ============================================================
app.post('/folders', async (req, res) => {
  const { imapHost, imapPort, imapSecure, username, password } = req.body;

  if (!imapHost || !username) {
    return res.json({ status: false, reason: 'imapHost and username required' });
  }

  let client;
  try {
    client = new ImapFlow({
      host: imapHost,
      port: imapPort || 993,
      secure: imapSecure !== false,
      auth: { user: username, pass: password },
      logger: false,
    });

    await client.connect();
    const folders = [];
    const lock = await client.getMailboxLock('INBOX');
    try {
      for await (const folder of client.list()) {
        folders.push({
          name: folder.name,
          path: folder.path,
          specialUse: folder.flags || [],
          delimiter: folder.delimiter,
        });
      }
    } finally {
      lock.release();
    }
    await client.logout();

    return res.json({ status: true, folders });
  } catch (e) {
    if (client) {
      try { await client.logout(); } catch (_) {}
    }
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// START SERVER
// ============================================================
app.listen(PORT, () => {
  console.log('========================================');
  console.log('  Mail Gateway Worker (ImapFlow + Nodemailer)');
  console.log('  Listening on port ' + PORT);
  console.log('  Django webhook: ' + DJANGO_WEBHOOK_URL);
  console.log('========================================');
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down mail worker...');
  process.exit(0);
});
process.on('SIGTERM', () => {
  console.log('\nShutting down mail worker...');
  process.exit(0);
});
