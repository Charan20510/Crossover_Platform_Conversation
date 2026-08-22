'use strict';
const assert = require('assert');
const { extractMessageText } = require('./sessionManager');

assert.strictEqual(extractMessageText({ conversation: 'hi' }), 'hi');
assert.strictEqual(extractMessageText({ extendedTextMessage: { text: 'hey' } }), 'hey');

assert.strictEqual(
  extractMessageText({ ephemeralMessage: { message: { extendedTextMessage: { text: 'gone soon' } } } }),
  'gone soon'
);

assert.strictEqual(
  extractMessageText({ viewOnceMessageV2: { message: { imageMessage: { caption: 'look' } } } }),
  'look'
);

assert.strictEqual(extractMessageText({ protocolMessage: {} }), '');
assert.strictEqual(extractMessageText(null), '');

assert.strictEqual(extractMessageText({ stickerMessage: {} }), '[Unsupported message: stickerMessage]');

console.log('extractMessageText: all checks passed');
