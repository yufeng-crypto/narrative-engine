"""
统一 LLM 调用客户端 - MiniMax API
"""
import os
import json
import time
import logging
import traceback
import httpx

MINIMAX_API_URL = "https://api.minimax.io/v1/text/chatcompletion_v2"
DEFAULT_MODEL = "MiniMax-M2.5"

_api_key = None
log = logging.getLogger("narrative_engine.llm_client")


def _load_env():
    """从 .env 文件加载环境变量（如果存在）"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    else:
        log.warning(".env 文件不存在，路径: %s", env_path)


def _get_api_key() -> str:
    global _api_key
    if _api_key is None:
        _load_env()
        _api_key = os.environ.get("MINIMAX_API_KEY")
        if not _api_key:
            raise RuntimeError(
                "未找到 MINIMAX_API_KEY\n"
                "请在 narrative_engine/.env 文件中设置：\n"
                "  MINIMAX_API_KEY=eyJ..."
            )
        log.info("API Key 已加载，前缀: %s...", _api_key[:12])
    return _api_key


def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> str:
    """普通文本调用"""
    api_key = _get_api_key()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "name": "MiniMax AI", "content": system_prompt},
            {"role": "user", "name": "user", "content": user_prompt},
        ],
        "max_tokens": 1024,
    }

    log.debug("── LLM 请求 ──────────────────────────────")
    log.debug("  模型: %s", model)
    log.debug("  API URL: %s", MINIMAX_API_URL)
    log.debug("  system_prompt (%d chars): %s", len(system_prompt), system_prompt[:200])
    log.debug("  user_prompt (%d chars): %s", len(user_prompt), user_prompt[:200])
    log.debug("  完整 payload: %s", json.dumps(payload, ensure_ascii=False))

    t0 = time.time()
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                MINIMAX_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        elapsed = time.time() - t0
        log.debug("  HTTP 状态: %s  耗时: %.2fs", resp.status_code, elapsed)
        log.debug("  响应原文: %s", resp.text[:2000])

        resp.raise_for_status()
        data = resp.json()

    except httpx.HTTPStatusError as e:
        log.error("HTTP 错误 %s: %s", e.response.status_code, e.response.text)
        raise
    except httpx.RequestError as e:
        log.error("网络请求失败: %s\n%s", e, traceback.format_exc())
        raise
    except Exception as e:
        log.error("未知错误: %s\n%s", e, traceback.format_exc())
        raise

    # MiniMax 用 base_resp.status_code 表示业务错误
    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        log.error(
            "MiniMax 业务错误 %s: %s\n完整响应: %s",
            base_resp.get("status_code"),
            base_resp.get("status_msg"),
            json.dumps(data, ensure_ascii=False),
        )
        raise RuntimeError(
            f"MiniMax API 错误 {base_resp.get('status_code')}: {base_resp.get('status_msg')}\n"
            f"完整响应: {json.dumps(data, ensure_ascii=False)}"
        )

    if "choices" not in data:
        log.error("响应缺少 choices 字段，完整响应: %s", json.dumps(data, ensure_ascii=False))
        raise RuntimeError(
            f"MiniMax 响应缺少 choices 字段，完整响应:\n{json.dumps(data, ensure_ascii=False)}"
        )

    content = data["choices"][0]["message"]["content"]
    log.debug("  回复 (%d chars): %s", len(content), content[:300])
    log.debug("── LLM 完成 (%.2fs) ─────────────────────", elapsed)
    return content


def call_llm_json(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> dict:
    """返回 JSON dict，自动解析"""
    system_prompt = system_prompt + "\n\n【重要】你的输出必须是合法的 JSON，不加任何 markdown 代码块，不加任何额外解释。"
    raw = call_llm(system_prompt, user_prompt, model)
    raw = raw.strip()
    # 去掉可能的 ```json ... ``` 包裹
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        result = json.loads(raw)
        log.debug("call_llm_json 解析成功，keys: %s", list(result.keys()) if isinstance(result, dict) else type(result))
        return result
    except json.JSONDecodeError:
        log.warning("JSON 解析失败，尝试提取 {} 块，原文: %s", raw[:500])
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                result = json.loads(raw[start:end])
                log.debug("降级解析成功")
                return result
            except Exception:
                pass
        log.error("JSON 完全解析失败，原文: %s", raw)
        return {"error": "JSON parse failed", "raw": raw}
