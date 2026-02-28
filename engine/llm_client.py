"""
统一 LLM 调用客户端 - MiniMax API
"""
import os
import json
import httpx

MINIMAX_API_URL = "https://api.minimax.io/v1/text/chatcompletion_v2"
DEFAULT_MODEL = "MiniMax-M2.5"

_api_key = None


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
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            MINIMAX_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    # MiniMax 用 base_resp.status_code 表示业务错误
    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise RuntimeError(
            f"MiniMax API 错误 {base_resp.get('status_code')}: {base_resp.get('status_msg')}\n"
            f"完整响应: {json.dumps(data, ensure_ascii=False)}"
        )
    if "choices" not in data:
        raise RuntimeError(
            f"MiniMax 响应缺少 choices 字段，完整响应:\n{json.dumps(data, ensure_ascii=False)}"
        )
    return data["choices"][0]["message"]["content"]


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
        return json.loads(raw)
    except json.JSONDecodeError:
        # 降级：尝试提取第一个 { } 块
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
        return {"error": "JSON parse failed", "raw": raw}
