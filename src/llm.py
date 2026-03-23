import os
import time
from typing import List, Dict, Tuple, Any, Optional

import requests

"""
统一的 LLM 客户端封装。

提供商/模型命名规则：'provider/model'，provider 大小写不敏感，model 保留大小写与路径。
当前支持：deepseek、siliconflow、ollama、blt、cstcloud（科技云）。
"""

# 单次实验级别的全局 token 统计（需由调用方在实验开始前手动 reset）
GLOBAL_TOKENS = {
    'prompt': 0,    # 提示词（prompt）部分 token
    'thinking': 0,  # 推理/思维链部分 token（reasoning_tokens）
    'content': 0,   # 可见输出部分 token（completion_tokens - reasoning_tokens）
    'total': 0,     # provider 返回的总 token（通常含 prompt + completion）
}
# 单次实验级别的全局时间统计（秒）
GLOBAL_TIME_SECONDS: float = 0.0

PRIMARY_LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_BLT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def reset_global_tokens():
    """重置本次实验的全局 token 统计。"""
    GLOBAL_TOKENS['prompt'] = 0
    GLOBAL_TOKENS['thinking'] = 0
    GLOBAL_TOKENS['content'] = 0
    GLOBAL_TOKENS['total'] = 0


def get_global_tokens() -> Dict[str, int]:
    """获取本次实验的全局 token 统计（thinking/content/total）。"""
    return dict(GLOBAL_TOKENS)


def reset_global_time():
    """重置本次实验的大模型总耗时统计（秒）。"""
    global GLOBAL_TIME_SECONDS
    GLOBAL_TIME_SECONDS = 0.0


def get_global_time() -> float:
    """获取本次实验的大模型总耗时（秒）。"""
    return float(GLOBAL_TIME_SECONDS)


class LLMClient:
    tokens = {
        'prompt': 0,
        'content': 0,
        'reasoning': 0,
        'total': 0,
    }

    def __init__(self, api_key: str, model: str, base_url: str):
        """
        初始化 LLM 客户端。

        :param api_key: API 密钥
        :param model: 模型名称
        :param base_url: API 的基础 URL
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._base_urls = self._normalize_base_urls([base_url])
        # 实例级别的累计统计（无需显式 reset；通常每个实验构造一个 client）
        self._call_index = 0
        self._cum_tokens = {
            'prompt': 0,
            'thinking': 0,
            'content': 0,
            'total': 0,
        }
        # 实例级别的累计耗时（秒）
        self._cum_time_seconds: float = 0.0
        self.kwargs: Dict[str, Any] = {
            'max_tokens': 4000,  # 更安全的默认值，避免超过部分模型上限
            'temperature': 0.6,
            'top_p': 0.3,
            'top_k': 50,
            'frequency_penalty': 0.5,
            'n': 1,
            'stream': False,
        }

    @staticmethod
    def _normalize_base_urls(urls: List[str | None]) -> List[str]:
        out: List[str] = []
        for url in urls:
            if not url:
                continue
            candidate = str(url).strip().rstrip("/")
            if candidate and candidate not in out:
                out.append(candidate)
        return out

    def _iter_request_bases(self) -> List[str]:
        return self._normalize_base_urls(self._base_urls)

    def _iter_retry_bases(self, total_attempts: int = 6) -> List[str]:
        bases = self._iter_request_bases()
        if total_attempts <= 0:
            return []
        if not bases:
            return []

        if len(bases) == 1:
            return [bases[0]] * total_attempts

        attempts: List[str] = []
        for idx in range(total_attempts):
            attempts.append(bases[idx % len(bases)])
        return attempts

    def _provider_name(self, base_url: str | None = None) -> str:
        try:
            url = (base_url or self.base_url or '').lower()
            if 'deepseek' in url:
                return 'deepseek'
            if 'siliconflow' in url or 'siliconflow.cn' in url:
                return 'siliconflow'
            if 'gptbest' in url:
                return 'blt'
            if 'bltcy' in url or 'blt' in url:
                return 'blt'
            if 'ollama' in url or 'localhost' in url:
                return 'ollama'
            if 'cstcloud' in url or 'uni-api.cstcloud.cn' in url:
                return 'cstcloud'
        except Exception:
            pass
        return 'llm'

    def chat(self, messages: List[Dict[str, str]], response_format: Optional[Dict[str, Any]] = None) -> dict:
        """
        统一 Chat Completions 请求。

        :param messages: OpenAI 格式的消息列表
        :param response_format: 可选，结构化输出配置（柏拉图支持）
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        model_name = self.model
        if 'qwen3' in model_name.lower():
            if '/think' in model_name:
                self.kwargs['enable_thinking'] = True
                model_name = model_name.replace('/think', '')
            else:
                self.kwargs['enable_thinking'] = False
                model_name = model_name.replace('/think', '')

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        # 仅透传 OpenAI Chat Completions 兼容字段，避免提供商拒绝未知参数
        allowed_keys = {
            'max_tokens', 'temperature', 'top_p', 'n', 'stream',
            'presence_penalty', 'frequency_penalty', 'stop', 'logprobs',
            'tools', 'tool_choice', 'logit_bias',
            'response_format',
        }
        if isinstance(self.kwargs, dict):
            for k, v in self.kwargs.items():
                if k in allowed_keys:
                    payload[k] = v
        if response_format is not None:
            payload['response_format'] = response_format

        # 对输出 token 上限做保护（部分模型 4k 上限，统一取不超过 10000）
        try:
            if isinstance(payload.get('max_tokens'), int) and payload['max_tokens'] > 10000:
                payload['max_tokens'] = 10000
        except Exception:
            pass

        start_time = time.time()
        request_bases = self._iter_retry_bases(total_attempts=6)
        last_error: Exception | None = None
        for attempt_idx, req_base in enumerate(request_bases, start=1):
            request_url = f"{req_base.rstrip('/')}/chat/completions"
            try:
                response = requests.post(request_url, headers=headers, json=payload, timeout=120)
                response.raise_for_status()
                try:
                    response_data = response.json()
                except ValueError:
                    print("API 响应无法解析为 JSON，原始文本预览:", response.text[:500])
                    raise

                debug_raw = os.getenv("BLT_DEBUG_RAW") == "1" or os.getenv("LLM_DEBUG_RAW") == "1"
                if debug_raw and self._provider_name(req_base) == "blt":
                    print("[DEBUG] BLT 原始响应包:", response.text)

                if isinstance(response_data, dict) and 'error' in response_data:
                    err = response_data.get('error') or {}
                    print("API 返回错误:", {
                        'type': err.get('type'),
                        'code': err.get('code'),
                        'message': err.get('message') or err,
                    })
                    raise requests.exceptions.HTTPError(f"API error: {err}")

                if 'choices' not in response_data or not response_data['choices']:
                    print("API 响应不包含 choices 字段或为空：", str(response_data)[:500])
                    raise requests.exceptions.HTTPError("API response missing choices")

                message = response_data['choices'][0].get('message', {})
                content = message.get('content', '') or ''
                reasoning_content = message.get('reasoning_content', '') or ''

                usage = response_data.get('usage', {})
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                reasoning_tokens = 0
                if 'completion_tokens_details' in usage:
                    reasoning_tokens = usage['completion_tokens_details'].get('reasoning_tokens', 0)

                self.tokens['prompt'] += prompt_tokens
                self.tokens['content'] += completion_tokens - reasoning_tokens
                self.tokens['reasoning'] += reasoning_tokens
                self.tokens['total'] += total_tokens

                try:
                    GLOBAL_TOKENS['prompt'] += int(prompt_tokens)
                    GLOBAL_TOKENS['thinking'] += int(reasoning_tokens)
                    GLOBAL_TOKENS['content'] += int(completion_tokens - reasoning_tokens)
                    GLOBAL_TOKENS['total'] += int(total_tokens)
                except Exception:
                    pass

                try:
                    elapsed = time.time() - start_time
                    self._cum_time_seconds += float(elapsed)
                    try:
                        global GLOBAL_TIME_SECONDS
                        GLOBAL_TIME_SECONDS += float(elapsed)
                    except Exception:
                        pass

                    self._call_index += 1
                    self._cum_tokens['prompt'] += int(prompt_tokens)
                    self._cum_tokens['thinking'] += int(reasoning_tokens)
                    self._cum_tokens['content'] += int(completion_tokens - reasoning_tokens)
                    self._cum_tokens['total'] += int(total_tokens)

                    provider = self._provider_name(req_base)
                    header = f"[{provider}][{self.model}] 第{self._call_index}次"
                    line_cur = (
                        f"本次 tokens：prompt={int(prompt_tokens)}, thinking={int(reasoning_tokens)}, "
                        f"content={int(completion_tokens - reasoning_tokens)}, total={int(total_tokens)}"
                    )
                    line_cum = (
                        f"累计 tokens：prompt={self._cum_tokens['prompt']}, thinking={self._cum_tokens['thinking']}, "
                        f"content={self._cum_tokens['content']}, total={self._cum_tokens['total']}"
                    )
                    line_time = (
                        f"本次用时：{elapsed:.2f}s，"
                        f"累计用时：{self._cum_time_seconds:.2f}s"
                    )
                    print(header + "\n" + line_cur + "\n" + line_cum + "\n" + line_time)
                except Exception:
                    pass

                return {
                    "content": content,
                    "reasoning_content": reasoning_content,
                    "tokens": {
                        "prompt": prompt_tokens,
                        "content": completion_tokens - reasoning_tokens,
                        "reasoning": reasoning_tokens,
                        "total": total_tokens
                    }
                }

            except Exception as e:
                last_error = e
                if attempt_idx < len(request_bases):
                    next_base = request_bases[attempt_idx] if attempt_idx < len(request_bases) else ''
                    print(
                        f"请求失败（base={req_base}，第 {attempt_idx} 次），"
                        f"将回退到 {next_base}"
                    )
                    if hasattr(e, "response") and e.response is not None:
                        try:
                            print("错误详情(JSON):", e.response.json())
                        except ValueError:
                            try:
                                print("错误详情(TEXT):", e.response.text[:500])
                            except Exception:
                                pass
                    continue
                print(f"通过 requests 调用 API 时出错: {e}")
                if hasattr(e, "response") and e.response is not None:
                    try:
                        print("错误详情(JSON):", e.response.json())
                    except ValueError:
                        try:
                            print("错误详情(TEXT):", e.response.text[:500])
                        except Exception:
                            pass
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM 请求未命中可用 base")

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        model: Optional[str] = None,
    ) -> dict:
        """重排序接口（默认不支持，只有 BLT 提供）。"""
        raise NotImplementedError("rerank 仅支持 BltClient，请使用 BltClient 调用。")


class DeepSeekClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.deepseek.com"):
        super().__init__(api_key=api_key, model=model, base_url=base_url)


class SiliconflowClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.siliconflow.cn/v1"):
        super().__init__(api_key=api_key, model=model, base_url=base_url)


class CSTCloudClient(LLMClient):
    """CSTCloud（科技云）提供商，OpenAI Chat Completions 兼容接口。

    默认基址：https://uni-api.cstcloud.cn/v1
    使用示例：model="CSTCloud/gpt-oss-120b" 或 "CSTCloud/qwen3:235b"
    建议环境变量：CSTCLOUD_API_KEY
    """
    def __init__(self, api_key: str, model: str, base_url: str = "https://uni-api.cstcloud.cn/v1"):
        super().__init__(api_key=api_key, model=model, base_url=base_url)


class ZhipuGLMClient(LLMClient):
    """智谱 GLM 提供商，OpenAI Chat Completions 兼容接口。

    默认基址：https://open.bigmodel.cn/api/paas/v4
    使用示例：model="glm-4-flash" 或 "glm-4"
    建议环境变量：ZHIPU_API_KEY
    """
    def __init__(self, api_key: str, model: str, base_url: str = "https://open.bigmodel.cn/api/paas/v4"):
        super().__init__(api_key=api_key, model=model, base_url=base_url)


SliconflowClient = SiliconflowClient


class OllamaClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str = "http://localhost:11111/v1"):
        super().__init__(api_key=api_key, model=model, base_url=base_url)


class BltClient(LLMClient):
    """BLT（柏拉图）网关，OpenAI Chat Completions 兼容接口。"""
    def __init__(self, api_key: str, model: str, base_url: str = None):
        legacy_base = base_url or os.getenv('BLT_API_BASE', DEFAULT_BLT_BASE_URL)
        primary_base = (
            os.getenv("LLM_PRIMARY_BASE_URL")
            or os.getenv("BLT_PRIMARY_BASE_URL")
            or os.getenv("GPTBEST_BASE_URL")
            or PRIMARY_LLM_BASE_URL
        ).strip() or PRIMARY_LLM_BASE_URL
        super().__init__(api_key=api_key, model=model, base_url=primary_base)
        self._base_urls = self._normalize_base_urls([primary_base, legacy_base])

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        model: Optional[str] = None,
    ) -> dict:
        """
        调用柏拉图 Rerank 接口（/v1/rerank）。

        :param query: 查询文本
        :param documents: 待排序文档列表
        :param top_n: 返回的 Top N（可选）
        :param model: 重排模型名（可选，默认使用 self.model）
        """
        if not query:
            raise ValueError("rerank: query 不能为空")
        if not documents:
            raise ValueError("rerank: documents 不能为空")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = int(top_n)

        request_bases = self._iter_retry_bases(total_attempts=6)
        last_error: Exception | None = None
        for attempt_idx, req_base in enumerate(request_bases, start=1):
            request_url = f"{req_base.rstrip('/')}/rerank"
            try:
                response = requests.post(request_url, headers=headers, json=payload, timeout=120)
                response.raise_for_status()
                try:
                    response_data = response.json()
                except ValueError:
                    print("Rerank 响应无法解析为 JSON，原始文本预览:", response.text[:500])
                    raise

                if isinstance(response_data, dict) and 'error' in response_data:
                    err = response_data.get('error') or {}
                    print("Rerank 返回错误:", {
                        'type': err.get('type'),
                        'code': err.get('code'),
                        'message': err.get('message') or err,
                    })
                    raise requests.exceptions.HTTPError(f"Rerank API error: {err}")

                return response_data
            except Exception as e:
                last_error = e
                if attempt_idx < len(request_bases):
                    next_base = request_bases[attempt_idx] if attempt_idx < len(request_bases) else ''
                    print(
                        f"Rerank 请求失败（base={req_base}，第 {attempt_idx} 次），"
                        f"将回退到 {next_base}"
                    )
                    continue
                print(f"通过 requests 调用 Rerank API 时出错: {e}")
                print("Rerank 请求摘要:", {
                    "url": request_url,
                    "model": payload.get("model"),
                    "query_len": len(query or ""),
                    "documents": len(documents),
                    "top_n": payload.get("top_n"),
                })
                if e.response is not None:
                    try:
                        print("错误详情(JSON):", e.response.json())
                    except ValueError:
                        try:
                            print("错误详情(TEXT):", e.response.text[:500])
                        except Exception:
                            pass
                else:
                    print("错误详情: 未收到服务端响应（可能是网络/SSL问题）。")
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("rerank 未命中可用 base")


def parse_provider_model(model_str: str) -> Tuple[str, str]:
    """
    解析模型字符串为 (provider, model)。

    规则：第一个 '/' 之前为提供商（大小写不敏感），之后的全部为模型名（大小写敏感，允许包含 '/').
    示例：
    - "deepseek/deepseek-chat" -> ("deepseek", "deepseek-chat")
    - "SiliconFlow/Qwen/Qwen3-8B" -> ("siliconflow", "Qwen/Qwen3-8B")
    - "ollama/llama3.1:8b" -> ("ollama", "llama3.1:8b")
    """
    if not isinstance(model_str, str) or '/' not in model_str:
        raise ValueError("缺少模型提供商：请使用 'provider/model' 格式，例如 'CSTCloud/gpt-oss-120b'")
    provider, model = model_str.split('/', 1)
    return provider.lower(), model


class ClientFactory:
    @staticmethod
    def from_env():
        """
        基于环境变量创建具体客户端。

        必填：
        - LLM_MODEL：形如 'provider/model'。
        选填：
        - LLM_API_KEY：通用 API key（优先级高于各 provider 专用 key）
        - LLM_BASE_URL：通用 base_url（优先级高于默认 base_url）
        """
        model_env = (os.getenv('LLM_MODEL') or '').strip()
        if not model_env:
            raise ValueError("缺少必要环境变量: LLM_MODEL（格式为 'provider/model'）")

        provider, model = parse_provider_model(model_env)
        api_key = (os.getenv('LLM_API_KEY') or '').strip() or None
        base_url = (os.getenv('LLM_BASE_URL') or '').strip() or None

        if provider == 'deepseek':
            base_url = base_url or "https://api.deepseek.com"
            return DeepSeekClient(api_key=api_key or os.getenv('DEEPSEEK_API_KEY', ''), model=model, base_url=base_url)
        if provider in ('siliconflow', 'silicon-flow', 'sflow'):
            base_url = base_url or "https://api.siliconflow.cn/v1"
            return SiliconflowClient(api_key=api_key or os.getenv('SILICONFLOW_API_KEY', ''), model=model, base_url=base_url)
        if provider == 'ollama':
            base_url = base_url or "http://localhost:11111/v1"
            return OllamaClient(api_key=api_key or '', model=model, base_url=base_url)
        if provider in ('blt', 'bltcy', 'plato'):
            return BltClient(api_key=api_key or os.getenv('BLT_API_KEY', ''), model=model, base_url=base_url or os.getenv('BLT_API_BASE', 'https://api.bltcy.ai/v1'))
        if provider in ('cstcloud', 'cst', 'cst-cloud', 'keji', 'keji-yun'):
            return CSTCloudClient(api_key=api_key or os.getenv('CSTCLOUD_API_KEY', ''), model=model, base_url=base_url or 'https://uni-api.cstcloud.cn/v1')
        if provider in ('zhipu', 'glm', 'zhipuglm', '智谱'):
            base_url = base_url or "https://open.bigmodel.cn/api/paas/v4"
            return ZhipuGLMClient(api_key=api_key or os.getenv('ZHIPU_API_KEY', ''), model=model, base_url=base_url)
        raise ValueError(f"不支持的提供商: {provider}，请使用 'deepseek'、'siliconflow'、'blt'、'cstcloud'、'ollama' 或 'zhipu/glm'")

    @staticmethod
    def from_config(_config: dict | None = None):
        """
        兼容旧调用入口，但不再读取 config 文件，统一从环境变量读取。
        """
        return ClientFactory.from_env()
