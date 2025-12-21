// 使用 EdgeOne Pages Functions 代理到原有 FastAPI 后端的 /api/history
// 这样前端可以直接访问边缘函数，由函数转发到 Python 服务。

export async function onRequestGet(context) {
  const { request, env } = context;

  const backendBase = env.BACKEND_BASE_URL;
  if (!backendBase) {
    return new Response('缺少环境变量 BACKEND_BASE_URL', { status: 500 });
  }

  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(incomingUrl.pathname + incomingUrl.search, backendBase);

  const headers = new Headers(request.headers);
  headers.set('host', new URL(backendBase).host);

  const resp = await fetch(targetUrl.toString(), {
    method: 'GET',
    headers,
  });

  return new Response(resp.body, {
    status: resp.status,
    headers: resp.headers,
  });
}

