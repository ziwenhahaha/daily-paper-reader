(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.DPRLLMConfigUtils = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const DEFAULT_PLATO_BASE_URL = 'https://api.bltcy.ai/v1';
  const DEFAULT_PLATO_CHAT_MODELS = [
    'gemini-3-flash-preview-thinking-1000',
    'deepseek-v3.2',
    'gpt-5-chat',
    'gemini-3-pro-preview',
  ];
  const OPENAI_COMPATIBLE_PRESETS = Object.freeze({
    deepseek: Object.freeze({
      key: 'deepseek',
      label: 'DeepSeek 官方',
      baseUrl: 'https://api.deepseek.com',
      models: Object.freeze(['deepseek-chat', 'deepseek-reasoner']),
    }),
    glm: Object.freeze({
      key: 'glm',
      label: 'GLM Coding Plan',
      baseUrl: 'https://open.bigmodel.cn/api/coding/paas/v4',
      models: Object.freeze(['GLM-4.7', 'GLM-5', 'GLM-4.6']),
    }),
    minimax: Object.freeze({
      key: 'minimax',
      label: 'MiniMax Coding Plan',
      baseUrl: 'https://api.minimaxi.com/v1',
      models: Object.freeze(['MiniMax-M2.5', 'MiniMax-M2.7', 'MiniMax-M2.1']),
    }),
    kimi: Object.freeze({
      key: 'kimi',
      label: 'Kimi 编程预设',
      baseUrl: 'https://api.moonshot.ai/v1',
      models: Object.freeze(['kimi-k2.5', 'kimi-k2-turbo-preview', 'kimi-k2-thinking']),
    }),
    openai: Object.freeze({
      key: 'openai',
      label: 'OpenAI 官方',
      baseUrl: 'https://api.openai.com/v1',
      models: Object.freeze(['gpt-4.1-mini', 'gpt-4.1']),
    }),
  });

  const normalizeText = (value) => String(value || '').trim();

  const normalizeBaseUrlForStorage = (value) => {
    let text = normalizeText(value).replace(/\/+$/g, '');
    if (!text) return '';
    text = text.replace(/\/chat\/completions$/i, '');
    return text.replace(/\/+$/g, '');
  };

  const buildChatCompletionsEndpoint = (value) => {
    const raw = normalizeText(value).replace(/\/+$/g, '');
    if (!raw) return '';
    if (/\/chat\/completions$/i.test(raw)) return raw;
    const normalized = normalizeBaseUrlForStorage(raw);
    if (!normalized) return '';
    if (/\/v\d+$/i.test(normalized)) {
      return `${normalized}/chat/completions`;
    }
    return `${normalized}/v1/chat/completions`;
  };

  const sanitizeModelList = (values, maxCount = 3) => {
    const rawList = Array.isArray(values) ? values : [values];
    const out = [];
    const seen = new Set();
    for (const value of rawList) {
      const parts = String(value || '')
        .split(/[\n,]+/)
        .map((item) => normalizeText(item))
        .filter(Boolean);
      for (const name of parts) {
        const key = name.toLowerCase();
        if (!key || seen.has(key)) continue;
        seen.add(key);
        out.push(name);
        if (out.length >= Math.max(Number(maxCount) || 0, 1)) {
          return out;
        }
      }
    }
    return out;
  };

  const resolveChatModels = (secret) => {
    const safeSecret = secret && typeof secret === 'object' ? secret : {};
    const chatList = Array.isArray(safeSecret.chatLLMs) ? safeSecret.chatLLMs : [];
    const models = [];
    const seen = new Set();
    chatList.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const baseUrl = normalizeBaseUrlForStorage(item.baseUrl || '');
      const apiKey = normalizeText(item.apiKey || '');
      const modelNames = sanitizeModelList(item.models || [], 99);
      if (!baseUrl || !apiKey || !modelNames.length) return;
      modelNames.forEach((name) => {
        const dedupeKey = `${name.toLowerCase()}\u0000${baseUrl}\u0000${apiKey}`;
        if (seen.has(dedupeKey)) return;
        seen.add(dedupeKey);
        models.push({
          name,
          apiKey,
          baseUrl,
        });
      });
    });
    return models;
  };

  const resolveSummaryLLM = (secret) => {
    const safeSecret = secret && typeof secret === 'object' ? secret : {};
    const summarized = safeSecret.summarizedLLM || {};
    const baseUrl = normalizeBaseUrlForStorage(summarized.baseUrl || '');
    const apiKey = normalizeText(summarized.apiKey || '');
    const model = normalizeText(summarized.model || '');
    if (baseUrl && apiKey && model) {
      return { baseUrl, apiKey, model };
    }

    const chatModels = resolveChatModels(safeSecret);
    if (!chatModels.length) return null;
    return {
      baseUrl: normalizeBaseUrlForStorage(chatModels[0].baseUrl || ''),
      apiKey: normalizeText(chatModels[0].apiKey || ''),
      model: normalizeText(chatModels[0].name || ''),
    };
  };

  const inferProviderType = (secret) => {
    const safeSecret = secret && typeof secret === 'object' ? secret : {};
    const llmProvider = safeSecret.llmProvider || {};
    const explicit = normalizeText(llmProvider.type || llmProvider.provider || '').toLowerCase();
    if (explicit === 'plato' || explicit === 'openai-compatible') {
      return explicit;
    }
    const summary = resolveSummaryLLM(safeSecret);
    if (!summary) return 'plato';
    if (/bltcy\.ai|gptbest\.vip/i.test(summary.baseUrl)) {
      return 'plato';
    }
    return 'openai-compatible';
  };

  const getOpenAICompatiblePreset = (key) => {
    const presetKey = normalizeText(key).toLowerCase();
    const preset = OPENAI_COMPATIBLE_PRESETS[presetKey];
    if (!preset) return null;
    return {
      key: preset.key,
      label: preset.label,
      baseUrl: preset.baseUrl,
      models: [...preset.models],
    };
  };

  const inferChatApiProfile = (baseUrl, model) => {
    const normalizedBaseUrl = normalizeBaseUrlForStorage(baseUrl || '').toLowerCase();
    const normalizedModel = normalizeText(model || '').toLowerCase();
    if (
      /(^|\/\/)(api\.)?deepseek\.com(?:$|\/)/i.test(normalizedBaseUrl)
      || normalizedModel.startsWith('deepseek-')
    ) {
      return 'deepseek';
    }
    if (/bltcy\.ai|gptbest\.vip/i.test(normalizedBaseUrl)) {
      return 'plato';
    }
    return 'generic-openai';
  };

  const shouldUseXApiKeyHeader = ({ baseUrl, model }) => {
    const normalizedBaseUrl = normalizeBaseUrlForStorage(baseUrl || '').toLowerCase();
    const normalizedModel = normalizeText(model || '').toLowerCase();
    if (
      /^minimax-/i.test(normalizedModel)
      || /(^|\/\/)api\.minimax(?:i)?\.(?:io|com)(?:$|\/)/i.test(normalizedBaseUrl)
    ) {
      return false;
    }
    return true;
  };

  const buildStreamingChatPayload = ({ baseUrl, model, messages }) => {
    const payload = {
      model: normalizeText(model),
      messages: Array.isArray(messages) ? messages : [],
      stream: true,
    };
    const profile = inferChatApiProfile(baseUrl, model);
    if (profile === 'plato') {
      payload.reasoning = { effort: 'medium' };
      payload.extra_body = { return_reasoning: true };
    } else if (profile === 'deepseek' && normalizeText(model).toLowerCase() === 'deepseek-reasoner') {
      payload.thinking = { type: 'enabled' };
    }
    return payload;
  };

  const buildConnectivityTestPayload = ({ baseUrl, model }) => {
    const normalizedModel = normalizeText(model);
    const normalizedBaseUrl = normalizeBaseUrlForStorage(baseUrl || '').toLowerCase();
    const wantsMaxCompletionTokens =
      /^glm-/i.test(normalizedModel)
      || /open\.bigmodel\.cn/.test(normalizedBaseUrl)
      || /thinking/i.test(normalizedModel)
      || /^kimi-/i.test(normalizedModel)
      || /^minimax-/i.test(normalizedModel)
      || normalizedModel.toLowerCase() === 'deepseek-reasoner';
    const payload = {
      model: normalizedModel,
      messages: [
        {
          role: 'system',
          content: 'Reply with exactly: hello world',
        },
        {
          role: 'user',
          content: 'hello world',
        },
      ],
      temperature: 0,
      max_tokens: 256,
    };
    if (wantsMaxCompletionTokens) {
      payload.max_completion_tokens = 256;
    }
    const profile = inferChatApiProfile(baseUrl, model);
    if (profile === 'deepseek' && normalizedModel.toLowerCase() === 'deepseek-reasoner') {
      payload.thinking = { type: 'disabled' };
    }
    return payload;
  };

  return {
    DEFAULT_PLATO_BASE_URL,
    DEFAULT_PLATO_CHAT_MODELS,
    OPENAI_COMPATIBLE_PRESETS,
    normalizeText,
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
  };
});
