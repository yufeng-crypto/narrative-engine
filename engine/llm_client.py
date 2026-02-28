"""
统一 LLM 调用客户端
使用 Anthropic SDK 调用 MiniMax Anthropic 兼容接口
"""
import os
import json
import time
import logging
import anthropic

MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
DEFAULT_MODEL = "MiniMax-M2.5"

_client = None
log = logging.getLogger("narrative_engine.llm_client")


def _load_env():
    """从 .env 文件加载环境变量（如果存在）"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    else:
        log.warning(".env 文件不存在，路径: %s", env_path)


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _load_env()
        api_key = os.environ.get("MINIMAX_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未找到 MINIMAX_API_KEY\n"
                "请在 .env 文件中设置：\n"
                "  MINIMAX_API_KEY=your-minimax-api-key"
            )
        log.info("API Key 已加载，前缀: %s...", api_key[:12])
        _client = anthropic.Anthropic(
            base_url=MINIMAX_BASE_URL,
            api_key=api_key,
        )
    return _client


def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> str:
    """普通文本调用，返回字符串"""
    # 非 MiniMax 模型自动回退，避免路由到错误端点
    if not model.startswith("MiniMax"):
        log.warning("模型 %s 不适用于 MiniMax 端点，自动替换为 %s", model, DEFAULT_MODEL)
        model = DEFAULT_MODEL

    client = _get_client()

    log.debug("── LLM 请求 ──────────────────────────────")
    log.debug("  模型: %s", model)
    log.debug("  Base URL: %s", MINIMAX_BASE_URL)
    log.debug("  system_prompt (%d chars): %s", len(system_prompt), system_prompt[:200])
    log.debug("  user_prompt (%d chars): %s", len(user_prompt), user_prompt[:200])

    t0 = time.time()
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed = time.time() - t0

    content = message.content[0].text
    log.debug("  耗时: %.2fs", elapsed)
    log.debug("  回复 (%d chars): %s", len(content), content[:300])
    log.debug("── LLM 完成 (%.2fs) ─────────────────────", elapsed)
    return content


def call_llm_json(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> dict:
    """返回 JSON dict，自动解析"""
    system_prompt = (
        system_prompt
        + "\n\n【重要】你的输出必须是合法的 JSON，不加任何 markdown 代码块，不加任何额外解释。"
    )
    raw = call_llm(system_prompt, user_prompt, model)
    raw = raw.strip()

    # 去掉可能的 ```json ... ``` 包裹
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        result = json.loads(raw)
        log.debug(
            "call_llm_json 解析成功，keys: %s",
            list(result.keys()) if isinstance(result, dict) else type(result),
        )
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
