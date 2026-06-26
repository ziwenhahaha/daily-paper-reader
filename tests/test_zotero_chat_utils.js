const assert = require('node:assert/strict');

const { inferSpeaker, buildChatLinesFromMessages } = require('../app/zotero-chat-utils.js');

assert.equal(inferSpeaker({ roleText: 'You', className: '' }), 'User');
assert.equal(inferSpeaker({ roleText: 'Assistant', className: '' }), 'AI');
assert.equal(inferSpeaker({ roleText: '', className: 'msg-content msg-content-user' }), 'User');
assert.equal(inferSpeaker({ roleText: '', className: 'msg-content msg-content-ai' }), 'AI');
assert.equal(inferSpeaker({ roleText: 'Thinking', className: 'msg-content thinking-history-content' }), '');
assert.equal(inferSpeaker({ roleText: '', className: 'thinking-history-content' }), '');

assert.deepEqual(
  buildChatLinesFromMessages([
    { role: 'user', content: 'Hello' },
    { role: 'ai', content: 'Formula $a=b$' },
    { role: 'thinking', content: 'ignore me' },
  ]),
  ['👤 User: Hello', '🤖 AI: Formula $a=b$'],
);

console.log('zotero chat utils tests passed');
