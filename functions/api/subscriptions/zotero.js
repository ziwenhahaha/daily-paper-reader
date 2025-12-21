// 使用 EdgeOne KV 实现新增 Zotero 账号（存储在单一 key 中）

const ZOTERO_KEY = 'subscriptions:zotero';

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

  const zid = (payload.zotero_id || '').trim();
  const key = (payload.api_key || '').trim();
  const alias = (payload.alias || '').trim();

  if (!zid || !key) {
    return jsonResponse({ detail: 'Zotero ID 和 Key 不能为空' }, 400);
  }
  if (!alias) {
    return jsonResponse({ detail: '备注为必填项' }, 400);
  }

  let current = [];
  try {
    const existing = await my_kv.get(ZOTERO_KEY);
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
    zotero_id: zid,
    api_key: key, // KV 中存储，对外返回时隐藏
    alias,
    created_at: now,
  });

  await my_kv.put(ZOTERO_KEY, JSON.stringify(current));

  return jsonResponse({ status: 'ok' });
}
