// 使用 EdgeOne KV 实现新增订阅关键词（存储在单一 key 中）

const KEYWORDS_KEY = 'subscriptions:keywords';

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=UTF-8',
      'Access-Control-Allow-Origin': '*',
    },
  });
}

export async function onRequestPost({ request }) {
  if (typeof my_kv === 'undefined') {
    return jsonResponse({ detail: 'KV 未配置：缺少 my_kv 绑定' }, 500);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ detail: '请求体必须是 JSON' }, 400);
  }

  const kw = (payload.keyword || '').trim();
  const alias = (payload.alias || '').trim();
  if (!kw) {
    return jsonResponse({ detail: '关键词不能为空' }, 400);
  }

  let current = [];
  try {
    const existing = await my_kv.get(KEYWORDS_KEY);
    if (existing) {
      const parsed = JSON.parse(existing);
      if (Array.isArray(parsed)) current = parsed;
    }
  } catch {
    // 解析失败则视为无历史
  }

  const now = new Date().toISOString();
  const nextId =
    current.reduce((max, item) => (item.id && item.id > max ? item.id : max), 0) + 1;

  current.push({
    id: nextId,
    keyword: kw,
    alias,
    created_at: now,
  });

  await my_kv.put(KEYWORDS_KEY, JSON.stringify(current));

  return jsonResponse({ status: 'ok' });
}
