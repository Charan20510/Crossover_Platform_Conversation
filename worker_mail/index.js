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

// Connect, run fn(client), always log out. Every IMAP endpoint below shares
// this so credential handling and cleanup live in exactly one place.
async function withImap(body, folder, fn) {
  const { imapHost, imapPort, imapSecure, username, password } = body;
  if (!imapHost || !username) {
    const err = new Error('imapHost and username required');
    err.clientError = true;
    throw err;
  }
  const client = new ImapFlow({
    host: imapHost,
    port: imapPort || 993,
    secure: imapSecure !== false,
    auth: { user: username, pass: password },
    logger: false,
  });
  await client.connect();
  try {
    if (folder) {
      const lock = await client.getMailboxLock(folder);
      try {
        return await fn(client);
      } finally {
        lock.release();
      }
    }
    return await fn(client);
  } finally {
    try { await client.logout(); } catch (_) {}
  }
}

// Flatten a bodyStructure tree into attachment metadata (no bytes). Includes
// the IMAP part id (node.part) — the only addressable handle for a later
// `client.download(uid, partId)` — which simpleParser's attachment list does
// not carry.
function collectAttachments(node, out = []) {
  if (!node) return out;
  if (node.disposition === 'attachment' || (node.dispositionParameters && node.dispositionParameters.filename)) {
    out.push({
      filename: (node.dispositionParameters && node.dispositionParameters.filename)
        || (node.parameters && node.parameters.name) || 'attachment',
      size: node.size || 0,
      contentType: node.type || 'application/octet-stream',
      partId: node.part || '',
    });
  }
  (node.childNodes || []).forEach(child => collectAttachments(child, out));
  return out;
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
    from, to, cc, bcc, subject, text, html, attachments, inReplyTo, references,
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
    // threading headers (reply / reply-all)
    if (inReplyTo) mailOptions.inReplyTo = inReplyTo;
    if (references) mailOptions.references = references;

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
  const { accountId, folder, limit, offset, unseen, search, notify } = req.body;
  const mailbox = folder || 'INBOX';

  try {
    const out = await withImap(req.body, mailbox, async (client) => {
      const searchCriteria = {};
      if (unseen) searchCriteria.seen = false;
      if (search) searchCriteria.or = [{ subject: search }, { from: search }, { body: search }];
      if (!unseen && !search) searchCriteria.all = true;

      const uids = await client.search(searchCriteria, { uid: true }) || [];
      const fetchLimit = Math.min(limit || 50, 200);
      const start = Math.max(offset || 0, 0);
      // uids come back ascending; newest first, then page from `offset`.
      const uidsToFetch = uids.slice().reverse().slice(start, start + fetchLimit);

      const emails = [];
      for (const uid of uidsToFetch) {
        const msg = await client.fetchOne(
          uid, { source: true, envelope: true, flags: true, bodyStructure: true, size: true }, { uid: true });
        if (!msg) continue;

        const envelope = msg.envelope || {};
        const flags = msg.flags || new Set();
        const addrs = (list) => (list || []).map(a => a.address).filter(Boolean).join(', ');

        let bodyText = '';
        let bodyHtml = '';
        let references = '';
        if (msg.source) {
          try {
            const raw = msg.source instanceof Buffer ? msg.source : Buffer.from(msg.source);
            const parsed = await simpleParser(raw);
            bodyText = parsed.text || '';
            bodyHtml = parsed.html || '';
            references = Array.isArray(parsed.references)
              ? parsed.references.join(' ') : (parsed.references || '');
          } catch (_) { /* unparseable body — headers are still useful */ }
        }
        // Always sourced from bodyStructure, not simpleParser's attachment
        // list — only bodyStructure carries a usable IMAP part id.
        const attachments = collectAttachments(msg.bodyStructure);

        emails.push({
          uid,
          messageId: envelope.messageId || '',
          subject: envelope.subject || '(no subject)',
          from: envelope.from && envelope.from[0] ? envelope.from[0].address : '',
          fromName: envelope.from && envelope.from[0] ? envelope.from[0].name || '' : '',
          to: addrs(envelope.to),
          cc: addrs(envelope.cc),
          inReplyTo: envelope.inReplyTo || '',
          references,
          date: envelope.date ? new Date(envelope.date).toISOString() : new Date().toISOString(),
          flags: Array.from(flags),
          isRead: flags.has('\\Seen'),
          isStarred: flags.has('\\Flagged'),
          isAnswered: flags.has('\\Answered'),
          isDraft: flags.has('\\Draft'),
          hasAttachments: attachments.length > 0,
          attachmentCount: attachments.length,
          attachments,
          text: bodyText.substring(0, 20000),
          html: bodyHtml.substring(0, 60000),
          size: msg.size || 0,
        });
      }
      return { total: uids.length, emails };
    });

    // Legacy webhook push (the token API's /mail/sync relies on it). The new
    // session views pass notify:false and upsert from the response instead.
    if (notify !== false) {
      for (const em of out.emails) {
        if (em.isRead) continue;
        try {
          await axios.post(DJANGO_WEBHOOK_URL, {
            event: 'incoming_email',
            accountId,
            uid: em.uid,
            messageId: em.messageId,
            subject: em.subject,
            from: em.from,
            to: em.to,
            text: em.text.substring(0, 1000),
            html: em.html.substring(0, 2000),
            hasAttachments: em.hasAttachments,
            attachmentCount: em.attachmentCount,
            folder: mailbox,
          });
        } catch (_) {}
      }
    }

    return res.json({ status: true, count: out.emails.length, total: out.total, emails: out.emails });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// FLAG / UNFLAG (\Seen, \Flagged, \Answered, \Draft)
// ============================================================
app.post('/flag', async (req, res) => {
  const { folder, uids, flags, add } = req.body;
  if (!Array.isArray(uids) || !uids.length || !Array.isArray(flags) || !flags.length) {
    return res.json({ status: false, reason: 'uids and flags required' });
  }
  try {
    const ok = await withImap(req.body, folder || 'INBOX', async (client) => {
      const range = uids.join(',');
      return add === false
        ? client.messageFlagsRemove(range, flags, { uid: true })
        : client.messageFlagsAdd(range, flags, { uid: true });
    });
    return res.json({ status: !!ok });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// MOVE (drives Delete -> Trash, Junk, Archive)
// ============================================================
app.post('/move', async (req, res) => {
  const { folder, uids, destination } = req.body;
  if (!Array.isArray(uids) || !uids.length || !destination) {
    return res.json({ status: false, reason: 'uids and destination required' });
  }
  try {
    const result = await withImap(req.body, folder || 'INBOX', (client) =>
      client.messageMove(uids.join(','), destination, { uid: true }));
    return res.json({ status: true, moved: (result && result.uidMap && result.uidMap.size) || uids.length });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// DELETE / EXPUNGE (only used to empty Trash)
// ============================================================
app.post('/delete', async (req, res) => {
  const { folder, uids } = req.body;
  if (!Array.isArray(uids) || !uids.length) {
    return res.json({ status: false, reason: 'uids required' });
  }
  try {
    const ok = await withImap(req.body, folder || 'INBOX', (client) =>
      client.messageDelete(uids.join(','), { uid: true }));
    return res.json({ status: !!ok });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// APPEND (save draft / copy outbound mail into Sent)
// ============================================================
app.post('/append', async (req, res) => {
  const { folder, raw, flags } = req.body;
  if (!folder || !raw) {
    return res.json({ status: false, reason: 'folder and raw required' });
  }
  try {
    const result = await withImap(req.body, null, (client) =>
      client.append(folder, Buffer.from(raw, 'utf8'), flags || [], new Date()));
    return res.json({ status: true, uid: (result && result.uid) || null, folder });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// DOWNLOAD ONE ATTACHMENT (by IMAP part id from collectAttachments)
// ============================================================
app.post('/attachment', async (req, res) => {
  const { folder, uid, partId, maxBytes } = req.body;
  if (!uid || !partId) {
    return res.json({ status: false, reason: 'uid and partId required' });
  }
  const cap = maxBytes || (10 * 1024 * 1024);
  try {
    const out = await withImap(req.body, folder || 'INBOX', async (client) => {
      const { meta, content } = await client.download(uid, partId, { uid: true });
      const chunks = [];
      let size = 0;
      for await (const chunk of content) {
        size += chunk.length;
        if (size > cap) {
          content.destroy();
          const err = new Error('attachment exceeds maxBytes');
          err.tooLarge = true;
          throw err;
        }
        chunks.push(chunk);
      }
      return {
        filename: (meta && meta.filename) || 'attachment',
        contentType: (meta && meta.contentType) || 'application/octet-stream',
        buffer: Buffer.concat(chunks),
      };
    });
    return res.json({
      status: true,
      filename: out.filename,
      contentType: out.contentType,
      size: out.buffer.length,
      contentB64: out.buffer.toString('base64'),
    });
  } catch (e) {
    return res.json({ status: false, reason: e.message });
  }
});

// ============================================================
// LIST IMAP FOLDERS
// ============================================================
app.post('/folders', async (req, res) => {
  try {
    const folders = await withImap(req.body, null, async (client) => {
      const out = [];
      for (const folder of await client.list()) {
        // ponytail: one STATUS round-trip per folder. Fine for a handful of
        // mailboxes; batch/cache it if someone has a hundred.
        let counts = {};
        try {
          counts = await client.status(folder.path, { messages: true, unseen: true });
        } catch (_) {}
        out.push({
          name: folder.name,
          path: folder.path,
          specialUse: folder.specialUse || '',
          flags: Array.from(folder.flags || []),
          delimiter: folder.delimiter || '/',
          messages: counts.messages || 0,
          unseen: counts.unseen || 0,
        });
      }
      return out;
    });
    return res.json({ status: true, folders });
  } catch (e) {
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
