import json
import os
import re
import time
from typing import List, Dict, Tuple, Any, Optional

import requests

"""
Unified LLM client wrapper.

Provider/model naming convention: 'provider/model'. Provider is case-insensitive;
model name preserves original casing and may contain slashes.
The current pipeline only supports DeepSeek; the local reranker does not use the LLM API.
"""

# Experiment-scoped global token counters (caller must reset before each experiment)
DEFAULT_MAX_OUTPUT_TOKENS = 393216


def resolve_max_output_tokens(default: int = DEFAULT_MAX_OUTPUT_TOKENS) -> int:
    raw = os.getenv("DPR_LLM_MAX_OUTPUT_TOKENS") or os.getenv("LLM_MAX_OUTPUT_TOKENS")
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except Exception:
        return default


GLOBAL_TOKENS = {
    'prompt': 0,    # Prompt tokens
    'thinking': 0,  # Reasoning/chain-of-thought tokens (reasoning_tokens)
    'content': 0,   # Visible output tokens (completion_tokens - reasoning_tokens)
    'total': 0,     # Total tokens reported by the provider (typically prompt + completion)
}
# Experiment-scoped global wall-clock time (seconds)
GLOBAL_TIME_SECONDS: float = 0.0

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def reset_global_tokens():
    """Reset global token counters for the current experiment."""
    GLOBAL_TOKENS['prompt'] = 0
    GLOBAL_TOKENS['thinking'] = 0
    GLOBAL_TOKENS['content'] = 0
    GLOBAL_TOKENS['total'] = 0


def get_global_tokens() -> Dict[str, int]:
    """Return global token counters for the current experiment (thinking/content/total)."""
    return dict(GLOBAL_TOKENS)


def reset_global_time():
    """Reset the global LLM wall-clock time counter (seconds) for the current experiment."""
    global GLOBAL_TIME_SECONDS
    GLOBAL_TIME_SECONDS = 0.0


def get_global_time() -> float:
    """Return the total LLM wall-clock time (seconds) for the current experiment."""
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
        Initialize the LLM client.

        :param api_key: API key
        :param model: Model name
        :param base_url: Base URL for the API endpoint
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._base_urls = self._normalize_base_urls([base_url])
        # Per-instance cumulative stats (no explicit reset needed; typically one client per experiment)
        self._call_index = 0
        self._cum_tokens = {
            'prompt': 0,
            'thinking': 0,
            'content': 0,
            'total': 0,
        }
        # Per-instance cumulative wall-clock time (seconds)
        self._cum_time_seconds: float = 0.0
        self.kwargs: Dict[str, Any] = {
            'max_tokens': resolve_max_output_tokens(),
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

    @staticmethod
    def _build_chat_completions_url(base_url: str | None) -> str:
        raw = str(base_url or "").strip().rstrip("/")
        if not raw:
            raise ValueError("No usable LLM base_url provided")
        if raw.lower().endswith("/chat/completions"):
            return raw
        if re.search(r"/v\d+$", raw, re.IGNORECASE):
            return f"{raw}/chat/completions"
        return f"{raw}/v1/chat/completions"

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
            model = str(self.model or '').strip().lower()
            if 'deepseek' in url:
                return 'deepseek'
            if model.startswith('deepseek-'):
                return 'deepseek'
        except Exception:
            pass
        return 'llm'

    @staticmethod
    def _is_authentication_error(exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code in (401, 403):
            return True
        message = str(exc or "").lower()
        return any(token in message for token in (
            "authentication fails",
            "invalid api key",
            "authorization required",
            "unauthorized",
        ))

    @staticmethod
    def _extract_text_content(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                text = LLMClient._extract_text_content(item)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        if isinstance(value, dict):
            for key in ("text", "content", "value"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    return text
        return ""

    @staticmethod
    def _strip_json_wrappers(text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _repair_json_suffix(text: str) -> str:
        if not text:
            return text

        stack: List[str] = []
        in_str = False
        escaped = False

        for ch in text:
            if in_str:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
            elif ch == '{':
                stack.append('}')
            elif ch == '[':
                stack.append(']')
            elif ch in ('}', ']'):
                if stack and stack[-1] == ch:
                    stack.pop()

        repaired = text
        if in_str:
            repaired += '"'
        if stack:
            repaired += ''.join(reversed(stack))
        repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
        return repaired

    @classmethod
    def parse_json_content(cls, text: str) -> Any:
        raw = cls._strip_json_wrappers((text or "").strip())
        if not raw:
            return None

        decoder = json.JSONDecoder()
        candidates: List[str] = []
        first_obj = raw.find("{")
        last_obj = raw.rfind("}")
        first_arr = raw.find("[")
        last_arr = raw.rfind("]")
        if first_obj != -1:
            candidates.append(raw[first_obj:])
            if last_obj != -1 and last_obj >= first_obj:
                candidates.append(raw[first_obj:last_obj + 1])
        if first_arr != -1:
            candidates.append(raw[first_arr:])
            if last_arr != -1 and last_arr >= first_arr:
                candidates.append(raw[first_arr:last_arr + 1])
        candidates.append(raw)

        seen: set[str] = set()
        last_exc: Exception | None = None
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                obj, _idx = decoder.raw_decode(candidate)
                return obj
            except Exception as exc:
                last_exc = exc
                repaired = cls._repair_json_suffix(candidate)
                if repaired == candidate:
                    continue
                try:
                    return json.loads(repaired)
                except Exception as exc2:
                    last_exc = exc2

        raise ValueError(f"Model did not return valid JSON: {raw[:500]}") from last_exc

    @staticmethod
    def build_json_schema_response_format(
        schema_name: str,
        schema: Dict[str, Any],
        strict: bool = True,
    ) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": bool(strict),
            },
        }

    @staticmethod
    def build_json_object_response_format() -> Dict[str, str]:
        return {"type": "json_object"}

    def _structured_response_format_names(
        self,
        allow_json_object_fallback: bool,
    ) -> List[str]:
        """
        Select the structured output format based on the primary endpoint.

        DeepSeek's stable JSON Output entry point is json_object, so json_schema is not
        sent by default. Override via DPR_LLM_STRUCTURED_FORMAT / LLM_STRUCTURED_FORMAT:
        - json_schema: force json_schema, then fall back to json_object if allowed
        - json_object: force json_object
        - auto: use default logic
        """
        if not allow_json_object_fallback:
            return ["json_schema"]

        override = (
            os.getenv("DPR_LLM_STRUCTURED_FORMAT")
            or os.getenv("LLM_STRUCTURED_FORMAT")
            or ""
        ).strip().lower().replace("-", "_")
        if override in ("prompt_only", "prompt", "none", "text"):
            return ["prompt_only"]
        if override in ("json_object", "object", "json"):
            return ["json_object", "prompt_only"]
        if override in ("json_schema", "schema", "structured"):
            return ["json_schema", "json_object", "prompt_only"]

        return ["json_object", "prompt_only"]

    @staticmethod
    def _messages_contain_json_instruction(messages: List[Dict[str, str]]) -> bool:
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str) and "json" in content.lower():
                return True
        return False

    @classmethod
    def _ensure_json_instruction(
        cls,
        messages: List[Dict[str, str]],
        format_name: str,
    ) -> List[Dict[str, str]]:
        if format_name not in ("json_object", "prompt_only"):
            return messages
        if cls._messages_contain_json_instruction(messages):
            return messages
        return [
            {
                "role": "system",
                "content": "Output valid JSON only. Do not output Markdown, code fences, or explanatory text.",
            },
            *(messages or []),
        ]

    @classmethod
    def _validate_json_schema_subset(
        cls,
        value: Any,
        schema: Dict[str, Any],
        path: str = "$",
    ) -> str | None:
        if not isinstance(schema, dict):
            return None

        expected_type = schema.get("type")
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        expected_types = [item for item in expected_types if isinstance(item, str)]

        def type_matches(type_name: str) -> bool:
            if type_name == "object":
                return isinstance(value, dict)
            if type_name == "array":
                return isinstance(value, list)
            if type_name == "string":
                return isinstance(value, str)
            if type_name == "number":
                return isinstance(value, (int, float)) and not isinstance(value, bool)
            if type_name == "integer":
                return isinstance(value, int) and not isinstance(value, bool)
            if type_name == "boolean":
                return isinstance(value, bool)
            if type_name == "null":
                return value is None
            return True

        if expected_types and not any(type_matches(type_name) for type_name in expected_types):
            return f"{path}: expected type {expected_types}, got {type(value).__name__}"

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            return f"{path}: value is not in enum"

        if expected_type == "object" or isinstance(value, dict):
            if not isinstance(value, dict):
                return f"{path}: expected object"
            properties = schema.get("properties")
            properties = properties if isinstance(properties, dict) else {}
            required = schema.get("required")
            required = required if isinstance(required, list) else []
            for key in required:
                if isinstance(key, str) and key not in value:
                    return f"{path}.{key}: missing required field"
            if schema.get("additionalProperties") is False:
                extra = sorted(set(value.keys()) - set(properties.keys()))
                if extra:
                    return f"{path}: unexpected fields {extra}"
            for key, child_schema in properties.items():
                if key not in value:
                    continue
                err = cls._validate_json_schema_subset(value[key], child_schema, f"{path}.{key}")
                if err:
                    return err

        if expected_type == "array" or isinstance(value, list):
            if not isinstance(value, list):
                return f"{path}: expected array"
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for idx, item in enumerate(value):
                    err = cls._validate_json_schema_subset(item, item_schema, f"{path}[{idx}]")
                    if err:
                        return err

        return None

    def _build_response_format_by_name(
        self,
        format_name: str,
        schema_name: str,
        schema: Dict[str, Any],
        strict: bool,
    ) -> Dict[str, Any] | None:
        if format_name == "json_schema":
            return self.build_json_schema_response_format(
                schema_name=schema_name,
                schema=schema,
                strict=strict,
            )
        if format_name == "json_object":
            return self.build_json_object_response_format()
        if format_name == "prompt_only":
            return None
        raise ValueError(f"Unknown structured output format: {format_name}")

    @staticmethod
    def _is_structured_output_unsupported_error(error: Exception) -> bool:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        text = ""
        if response is not None:
            try:
                text = response.text or ""
            except Exception:
                text = ""
        if not text:
            text = str(error or "")
        lowered = text.lower()
        has_target = any(token in lowered for token in (
            "response_format",
            "json_schema",
            "json object",
            "json_object",
        ))
        has_signal = any(token in lowered for token in (
            "unsupported",
            "not support",
            "not supported",
            "invalid",
            "unknown",
            "unrecognized",
            "extra inputs",
            "unexpected",
            "must be one of",
            "one of",
            "allowed values",
            "enum",
        ))
        if has_target and has_signal:
            return True
        if (
            status_code in (400, 404, 415, 422)
            and "response_format" in lowered
            and any(token in lowered for token in ("json_object", "json_schema", "text"))
        ):
            return True
        if status_code in (400, 404, 415, 422) and "response_format" in lowered:
            return True
        return False

    def chat(self, messages: List[Dict[str, str]], response_format: Optional[Dict[str, Any]] = None) -> dict:
        """
        Unified Chat Completions request.

        :param messages: Message list in OpenAI format
        :param response_format: Optional structured output config (DeepSeek JSON mode)
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
        # Only forward OpenAI Chat Completions-compatible fields to avoid provider rejecting unknown params
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

        # Guard against exceeding the output token limit; DeepSeek V4 supports longer output, defaulting to 384K.
        try:
            max_output_tokens = resolve_max_output_tokens()
            if isinstance(payload.get('max_tokens'), int) and payload['max_tokens'] > max_output_tokens:
                payload['max_tokens'] = max_output_tokens
        except Exception:
            pass

        start_time = time.time()
        request_bases = self._iter_retry_bases(total_attempts=6)
        last_error: Exception | None = None
        for attempt_idx, req_base in enumerate(request_bases, start=1):
            request_url = self._build_chat_completions_url(req_base)
            try:
                response = requests.post(request_url, headers=headers, json=payload, timeout=120)
                response.raise_for_status()
                try:
                    response_data = response.json()
                except ValueError:
                    print("API response could not be parsed as JSON, raw preview:", response.text[:500])
                    raise

                debug_raw = os.getenv("LLM_DEBUG_RAW") == "1"
                if debug_raw:
                    print("[DEBUG] LLM raw response:", response.text)

                if isinstance(response_data, dict) and 'error' in response_data:
                    err = response_data.get('error') or {}
                    print("API returned error:", {
                        'type': err.get('type'),
                        'code': err.get('code'),
                        'message': err.get('message') or err,
                    })
                    raise requests.exceptions.HTTPError(f"API error: {err}")

                if 'choices' not in response_data or not response_data['choices']:
                    print("API response missing or empty 'choices' field:", str(response_data)[:500])
                    raise requests.exceptions.HTTPError("API response missing choices")

                choice = response_data['choices'][0] if isinstance(response_data['choices'][0], dict) else {}
                message = choice.get('message', {}) if isinstance(choice, dict) else {}
                content = self._extract_text_content(message.get('content'))
                reasoning_content = self._extract_text_content(message.get('reasoning_content'))
                refusal = str(message.get('refusal') or '').strip()
                finish_reason = choice.get('finish_reason') if isinstance(choice, dict) else None

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
                    header = f"[{provider}][{self.model}] call #{self._call_index}"
                    line_cur = (
                        f"current tokens: prompt={int(prompt_tokens)}, thinking={int(reasoning_tokens)}, "
                        f"content={int(completion_tokens - reasoning_tokens)}, total={int(total_tokens)}"
                    )
                    line_cum = (
                        f"cumulative tokens: prompt={self._cum_tokens['prompt']}, thinking={self._cum_tokens['thinking']}, "
                        f"content={self._cum_tokens['content']}, total={self._cum_tokens['total']}"
                    )
                    line_time = (
                        f"elapsed: {elapsed:.2f}s, "
                        f"total elapsed: {self._cum_time_seconds:.2f}s"
                    )
                    print(header + "\n" + line_cur + "\n" + line_cum + "\n" + line_time)
                except Exception:
                    pass

                return {
                    "content": content,
                    "raw_content": message.get('content'),
                    "reasoning_content": reasoning_content,
                    "refusal": refusal,
                    "finish_reason": finish_reason,
                    "message": message,
                    "raw_response": response_data,
                    "tokens": {
                        "prompt": prompt_tokens,
                        "content": completion_tokens - reasoning_tokens,
                        "reasoning": reasoning_tokens,
                        "total": total_tokens
                    }
                }

            except Exception as e:
                last_error = e
                if self._is_authentication_error(e):
                    print(
                        "LLM authentication failed: the current API key is invalid or lacks permission. "
                        "Please update the DeepSeek API key in your local config and retry."
                    )
                    if hasattr(e, "response") and e.response is not None:
                        try:
                            print("Error details (JSON):", e.response.json())
                        except ValueError:
                            try:
                                print("Error details (TEXT):", e.response.text[:500])
                            except Exception:
                                pass
                    raise
                if response_format is not None and self._is_structured_output_unsupported_error(e):
                    raise
                if attempt_idx < len(request_bases):
                    next_base = request_bases[attempt_idx] if attempt_idx < len(request_bases) else ''
                    print(
                        f"Request failed (base={req_base}, attempt {attempt_idx}), "
                        f"falling back to {next_base}"
                    )
                    if hasattr(e, "response") and e.response is not None:
                        try:
                            print("Error details (JSON):", e.response.json())
                        except ValueError:
                            try:
                                print("Error details (TEXT):", e.response.text[:500])
                            except Exception:
                                pass
                    continue
                print(f"Error calling API via requests: {e}")
                if hasattr(e, "response") and e.response is not None:
                    try:
                        print("Error details (JSON):", e.response.json())
                    except ValueError:
                        try:
                            print("Error details (TEXT):", e.response.text[:500])
                        except Exception:
                            pass
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM request exhausted all available base URLs")

    def chat_structured(
        self,
        messages: List[Dict[str, str]],
        schema_name: str,
        schema: Dict[str, Any],
        *,
        strict: bool = True,
        allow_json_object_fallback: bool = True,
    ) -> Dict[str, Any]:
        attempts: List[Tuple[str, Dict[str, Any] | None]] = [
            (
                format_name,
                self._build_response_format_by_name(
                    format_name=format_name,
                    schema_name=schema_name,
                    schema=schema,
                    strict=strict,
                ),
            )
            for format_name in self._structured_response_format_names(
                allow_json_object_fallback=allow_json_object_fallback,
            )
        ]

        last_error: Exception | None = None
        for idx, (format_name, response_format) in enumerate(attempts):
            try:
                request_messages = self._ensure_json_instruction(messages, format_name)
                response = self.chat(messages=request_messages, response_format=response_format)
            except Exception as exc:
                last_error = exc
                if (
                    idx + 1 < len(attempts)
                    and response_format is not None
                    and self._is_structured_output_unsupported_error(exc)
                ):
                    print(
                        f"[INFO] Structured Outputs not supported, falling back to {attempts[idx + 1][0]}."
                    )
                    continue
                raise

            parsed = None
            parse_error: Exception | None = None
            if not response.get("refusal"):
                content = str(response.get("content") or "").strip()
                if content:
                    try:
                        parsed = self.parse_json_content(content)
                    except Exception as exc:
                        parse_error = exc
                    if parsed is not None and parse_error is None:
                        schema_error = self._validate_json_schema_subset(parsed, schema)
                        if schema_error:
                            parse_error = ValueError(f"JSON schema validation failed: {schema_error}")

            if parse_error is not None and idx + 1 < len(attempts):
                print(
                    f"[INFO] {format_name} response failed JSON validation, "
                    f"falling back to {attempts[idx + 1][0]}."
                )
                continue

            structured = dict(response)
            structured["parsed"] = parsed
            structured["parse_error"] = parse_error
            structured["response_format_used"] = format_name
            return structured

        if last_error is not None:
            raise last_error
        raise RuntimeError("Structured output request exhausted all available formats")

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        model: Optional[str] = None,
    ) -> dict:
        """Reranking does not use the remote LLM API; use the local reranker instead."""
        raise NotImplementedError("Remote rerank is disabled. Use the local reranker in src/3.rank_papers.py.")


class DeepSeekClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str = DEFAULT_DEEPSEEK_BASE_URL):
        super().__init__(api_key=api_key, model=model, base_url=base_url)


def parse_provider_model(model_str: str) -> Tuple[str, str]:
    """
    Parse a model string into (provider, model).

    Rule: everything before the first '/' is the provider (case-insensitive);
    everything after is the model name (case-sensitive, may contain '/').
    Example:
    - "deepseek/deepseek-v4-flash" -> ("deepseek", "deepseek-v4-flash")
    """
    if not isinstance(model_str, str) or '/' not in model_str:
        raise ValueError("Missing model provider: use the format 'deepseek/model', e.g. 'deepseek/deepseek-v4-flash'")
    provider, model = model_str.split('/', 1)
    return provider.lower(), model


class ClientFactory:
    @staticmethod
    def from_env():
        """
        Create a client from environment variables.

        Required:
        - LLM_MODEL: in the form 'provider/model'.
        Optional:
        - LLM_API_KEY: generic API key (takes precedence over provider-specific keys)
        - LLM_BASE_URL: generic base URL (takes precedence over the default)
        """
        model_env = (os.getenv('LLM_MODEL') or '').strip()
        if not model_env:
            raise ValueError("Missing required environment variable: LLM_MODEL (format: 'deepseek/model')")

        provider, model = parse_provider_model(model_env)
        api_key = (os.getenv('LLM_API_KEY') or '').strip() or None
        base_url = (os.getenv('LLM_BASE_URL') or '').strip() or None

        if provider == 'deepseek':
            base_url = base_url or DEFAULT_DEEPSEEK_BASE_URL
            return DeepSeekClient(api_key=api_key or os.getenv('DEEPSEEK_API_KEY', ''), model=model, base_url=base_url)
        raise ValueError(f"Only DeepSeek API is currently supported. Use 'deepseek/<model>', got provider={provider}")

    @staticmethod
    def from_config(_config: dict | None = None):
        """
        Legacy entry point kept for backward compatibility; config is ignored and
        all settings are now read from environment variables.
        """
        return ClientFactory.from_env()
