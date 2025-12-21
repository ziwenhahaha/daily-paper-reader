// 使用 EdgeOne KV 实现订阅查询（简化版）：
// - 关键词列表存储在单一 key：subscriptions:keywords
// - Zotero 账号列表存储在单一 key：subscriptions:zotero

const KEYWORDS_KEY = 'subscriptions:keywords';
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

export async function onRequestGet() {
  if (typeof my_kv === 'undefined') {
    return jsonResponse({ detail: 'KV 未配置：缺少 my_kv 绑定' }, 500);
  }

  let keywords = [];
  let zoteroAccounts = [];

  try {
    const kwStr = await my_kv.get(KEYWORDS_KEY);
    if (kwStr) {
      const parsed = JSON.parse(kwStr);
      if (Array.isArray(parsed)) {
        keywords = parsed;
      }
    }
  } catch {
    // 忽略解析错误，返回空列表
  }

  try {
    const zStr = await my_kv.get(ZOTERO_KEY);
    if (zStr) {
      const parsed = JSON.parse(zStr);
      if (Array.isArray(parsed)) {
        zoteroAccounts = parsed.map((item) => {
          const clone = { ...item };
          delete clone.api_key; // 与原后端保持一致，不返回 api_key
          return clone;
        });
      }
    }
  } catch {
    // 忽略解析错误
  }

  // id 升序
  keywords.sort((a, b) => (a.id || 0) - (b.id || 0));
  zoteroAccounts.sort((a, b) => (a.id || 0) - (b.id || 0));

  return jsonResponse({
    keywords,
    tracked_papers: [], // 后续迁移 /api/arxiv_track 后再填充
    zotero_accounts: zoteroAccounts,
  });
}
