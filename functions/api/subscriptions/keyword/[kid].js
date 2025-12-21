// 使用 EdgeOne KV 实现删除订阅关键词：DELETE /api/subscriptions/keyword/{kid}

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

export async function onRequestDelete({ params }) {
  if (typeof my_kv === 'undefined') {
    return jsonResponse({ detail: 'KV 未配置：缺少 my_kv 绑定' }, 500);
  }

  const idStr = params && params.kid;
  const id = parseInt(idStr || '', 10);
  if (!id) {
    return jsonResponse({ detail: '缺少或非法的关键词 ID' }, 400);
  }

  let current = [];
  try {
    const existing = await my_kv.get(KEYWORDS_KEY);
    if (existing) {
      const parsed = JSON.parse(existing);
      if (Array.isArray(parsed)) current = parsed;
    }
  } catch {
    // 忽略解析错误，当作空列表处理
  }

  const next = current.filter((item) => item.id !== id);
  await my_kv.put(KEYWORDS_KEY, JSON.stringify(next));

  return jsonResponse({ status: 'ok' });
}
