const assert = require('node:assert/strict');

const {
  normalizeBaseUrlForStorage,
  buildChatCompletionsEndpoint,
  sanitizeModelList,
  resolveChatModels,
  resolveSummaryLLM,
  inferProviderType,
  getOpenAICompatiblePreset,
  inferChatApiProfile,
  shouldUseXApiKeyHeader,
  buildStreamingChatPayload,
  buildConnectivityTestPayload,
} = require('../app/llm-config-utils.js');

function testNormalizeBaseUrlForStorage() {
  assert.equal(
    normalizeBaseUrlForStorage('https://api.example.com/v1/chat/completions'),
    'https://api.example.com/v1',
  );
  assert.equal(
    normalizeBaseUrlForStorage('https://api.example.com/v1/'),
    'https://api.example.com/v1',
  );
}

function testBuildChatCompletionsEndpoint() {
  assert.equal(
    buildChatCompletionsEndpoint('https://api.example.com/v1'),
    'https://api.example.com/v1/chat/completions',
  );
  assert.equal(
    buildChatCompletionsEndpoint('https://api.example.com/custom-root'),
    'https://api.example.com/custom-root/v1/chat/completions',
  );
}

function testSanitizeModelList() {
  assert.deepEqual(
    sanitizeModelList(['gpt-4o', ' gpt-4o ', 'qwen-max', 'glm-4.5', 'extra'], 3),
    ['gpt-4o', 'qwen-max', 'glm-4.5'],
  );
}

function testResolveChatModelsAndSummary() {
  const secret = {
    summarizedLLM: {
      apiKey: 'sk-summary',
      baseUrl: 'https://api.example.com/v1',
      model: 'gpt-4.1-mini',
    },
    chatLLMs: [
      {
        apiKey: 'sk-chat',
        baseUrl: 'https://api.example.com/v1/',
        models: ['gpt-4.1-mini', 'claude-sonnet-4'],
      },
    ],
  };

  const chatModels = resolveChatModels(secret);
  assert.equal(chatModels.length, 2);
  assert.deepEqual(chatModels.map((item) => item.name), [
    'gpt-4.1-mini',
    'claude-sonnet-4',
  ]);

  const summary = resolveSummaryLLM(secret);
  assert.equal(summary.model, 'gpt-4.1-mini');
  assert.equal(summary.baseUrl, 'https://api.example.com/v1');
}

function testInferProviderType() {
  assert.equal(
    inferProviderType({
      summarizedLLM: {
        apiKey: 'sk',
        baseUrl: 'https://api.bltcy.ai/v1',
        model: 'gemini-3-flash-preview-thinking-1000',
      },
    }),
    'plato',
  );
  assert.equal(
    inferProviderType({
      summarizedLLM: {
        apiKey: 'sk',
        baseUrl: 'https://api.openai.com/v1',
        model: 'gpt-4.1-mini',
      },
    }),
    'openai-compatible',
  );
}

function testGetOpenAICompatiblePreset() {
  assert.deepEqual(
    getOpenAICompatiblePreset('deepseek'),
    {
      key: 'deepseek',
      label: 'DeepSeek 官方',
      baseUrl: 'https://api.deepseek.com',
      models: ['deepseek-chat', 'deepseek-reasoner'],
    },
  );
  assert.deepEqual(
    getOpenAICompatiblePreset('glm'),
    {
      key: 'glm',
      label: 'GLM Coding Plan',
      baseUrl: 'https://open.bigmodel.cn/api/coding/paas/v4',
      models: ['GLM-4.7', 'GLM-5', 'GLM-4.6'],
    },
  );
  assert.deepEqual(
    getOpenAICompatiblePreset('minimax'),
    {
      key: 'minimax',
      label: 'MiniMax Coding Plan',
      baseUrl: 'https://api.minimaxi.com/v1',
      models: ['MiniMax-M2.5', 'MiniMax-M2.7', 'MiniMax-M2.1'],
    },
  );
  assert.deepEqual(
    getOpenAICompatiblePreset('kimi'),
    {
      key: 'kimi',
      label: 'Kimi 编程预设',
      baseUrl: 'https://api.moonshot.ai/v1',
      models: ['kimi-k2.5', 'kimi-k2-turbo-preview', 'kimi-k2-thinking'],
    },
  );
}

function testInferChatApiProfile() {
  assert.equal(
    inferChatApiProfile('https://api.deepseek.com', 'deepseek-chat'),
    'deepseek',
  );
  assert.equal(
    inferChatApiProfile('https://api.bltcy.ai/v1', 'gpt-5-chat'),
    'plato',
  );
  assert.equal(
    inferChatApiProfile('https://api.openai.com/v1', 'gpt-4.1-mini'),
    'generic-openai',
  );
}

function testShouldUseXApiKeyHeader() {
  assert.equal(
    shouldUseXApiKeyHeader({
      baseUrl: 'https://api.minimaxi.com/v1',
      model: 'MiniMax-M2.5',
    }),
    false,
  );
  assert.equal(
    shouldUseXApiKeyHeader({
      baseUrl: 'https://api.openai.com/v1',
      model: 'gpt-4.1-mini',
    }),
    true,
  );
}

function testBuildStreamingChatPayload() {
  assert.deepEqual(
    buildStreamingChatPayload({
      baseUrl: 'https://api.deepseek.com',
      model: 'deepseek-chat',
      messages: [{ role: 'user', content: 'hi' }],
    }),
    {
      model: 'deepseek-chat',
      messages: [{ role: 'user', content: 'hi' }],
      stream: true,
    },
  );

  assert.deepEqual(
    buildStreamingChatPayload({
      baseUrl: 'https://api.deepseek.com',
      model: 'deepseek-reasoner',
      messages: [{ role: 'user', content: 'hi' }],
    }),
    {
      model: 'deepseek-reasoner',
      messages: [{ role: 'user', content: 'hi' }],
      stream: true,
      thinking: { type: 'enabled' },
    },
  );

  assert.deepEqual(
    buildStreamingChatPayload({
      baseUrl: 'https://api.bltcy.ai/v1',
      model: 'gpt-5-chat',
      messages: [{ role: 'user', content: 'hi' }],
    }),
    {
      model: 'gpt-5-chat',
      messages: [{ role: 'user', content: 'hi' }],
      stream: true,
      reasoning: { effort: 'medium' },
      extra_body: { return_reasoning: true },
    },
  );
}

function testBuildConnectivityTestPayload() {
  assert.deepEqual(
    buildConnectivityTestPayload({
      baseUrl: 'https://api.deepseek.com',
      model: 'deepseek-reasoner',
    }),
    {
      model: 'deepseek-reasoner',
      messages: [
        { role: 'system', content: 'Reply with exactly: hello world' },
        { role: 'user', content: 'hello world' },
      ],
      temperature: 0,
      max_tokens: 256,
      max_completion_tokens: 256,
      thinking: { type: 'disabled' },
    },
  );

  assert.deepEqual(
    buildConnectivityTestPayload({
      baseUrl: 'https://api.deepseek.com',
      model: 'deepseek-chat',
    }),
    {
      model: 'deepseek-chat',
      messages: [
        { role: 'system', content: 'Reply with exactly: hello world' },
        { role: 'user', content: 'hello world' },
      ],
      temperature: 0,
      max_tokens: 256,
    },
  );

  assert.deepEqual(
    buildConnectivityTestPayload({
      baseUrl: 'https://open.bigmodel.cn/api/coding/paas/v4',
      model: 'GLM-4.7',
    }),
    {
      model: 'GLM-4.7',
      messages: [
        { role: 'system', content: 'Reply with exactly: hello world' },
        { role: 'user', content: 'hello world' },
      ],
      temperature: 0,
      max_tokens: 256,
      max_completion_tokens: 256,
    },
  );
}

testNormalizeBaseUrlForStorage();
testBuildChatCompletionsEndpoint();
testSanitizeModelList();
testResolveChatModelsAndSummary();
testInferProviderType();
testGetOpenAICompatiblePreset();
testInferChatApiProfile();
testShouldUseXApiKeyHeader();
testBuildStreamingChatPayload();
testBuildConnectivityTestPayload();

console.log('llm config utils tests passed');
