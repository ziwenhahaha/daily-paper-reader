// 使用 EdgeOne KV 实现删除 Zotero 账号：DELETE /api/subscriptions/zotero/{zid}

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

export async function onRequestDelete({ params }) {
  if (typeof my_kv === 'undefined') {
    return jsonResponse({ detail: 'KV 未配置：缺少 my_kv 绑定' }, 500);
  }

  const idStr = params && params.zid;
  const id = parseInt(idStr || '', 10);
  if (!id) {
    return jsonResponse({ detail: '缺少或非法的 Zotero 记录 ID' }, 400);
  }

  let current = [];
  try {
    const existing = await my_kv.get(ZOTERO_KEY);
    if (existing) {
      const parsed = JSON.parse(existing);
      if (Array.isArray(parsed)) current = parsed;
    }
  } catch {
    // 解析失败则视为空列表
  }

  const next = current.filter((item) => item.id !== id);
  await my_kv.put(ZOTERO_KEY, JSON.stringify(next));

  return jsonResponse({ status: 'ok' });
}
