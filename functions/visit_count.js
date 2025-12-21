// EdgeOne Pages Functions 示例：使用 KV 存储简单的访问计数
// 参考官方文档中的示例：通过 my_kv 记录页面访问次数

export async function onRequest({ request, params, env }) {
  // my_kv 是在 EdgeOne Pages 项目中绑定的 KV 命名空间变量名
  const current = await my_kv.get('visitCount');
  let visitCount = Number(current || '0') + 1;

  await my_kv.put('visitCount', visitCount.toString());

  const res = JSON.stringify({
    visitCount,
  });

  return new Response(res, {
    headers: {
      'content-type': 'application/json; charset=UTF-8',
      'Access-Control-Allow-Origin': '*',
    },
  });
}

