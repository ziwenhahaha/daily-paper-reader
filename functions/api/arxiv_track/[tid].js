// 代理 DELETE /api/arxiv_track/{tid} 到原有 FastAPI 后端

export async function onRequestDelete(context) {
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
    method: 'DELETE',
    headers,
  });

  return new Response(resp.body, {
    status: resp.status,
    headers: resp.headers,
  });
}

