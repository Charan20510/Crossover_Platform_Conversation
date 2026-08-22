'use strict';
// Self-check for extractMessageText — run with: node worker/test_extract_message_text.js
const assert = require('assert');
const { extractMessageText } = require('./sessionManager');

assert.strictEqual(extractMessageText({ conversation: 'hi' }), 'hi');
assert.strictEqual(extractMessageText({ extendedTextMessage: { text: 'hey' } }), 'hey');

// ephemeral (disappearing messages) wraps the real content one level deeper
assert.strictEqual(
  extractMessageText({ ephemeralMessage: { message: { extendedTextMessage: { text: 'gone soon' } } } }),
  'gone soon'
);

// view-once media wraps an imageMessage with a caption
assert.strictEqual(
  extractMessageText({ viewOnceMessageV2: { message: { imageMessage: { caption: 'look' } } } }),
  'look'
);

// protocol-only payloads stay silent (unchanged from before)
assert.strictEqual(extractMessageText({ protocolMessage: {} }), '');
assert.strictEqual(extractMessageText(null), '');

// genuinely non-text content gets a placeholder instead of a blank body
assert.strictEqual(extractMessageText({ stickerMessage: {} }), '[Unsupported message: stickerMessage]');

console.log('extractMessageText: all checks passed');
