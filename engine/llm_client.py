"""
统一 LLM 调用客户端，支持 JSON 结构化输出
"""
import os
import json
import anthropic

_client = None


def _load_env():
    """从 .env 文件加载环境变量（如果存在）"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _load_env()
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        if not api_key:
            raise RuntimeError(
                "未找到 ANTHROPIC_API_KEY\n"
                "请在 narrative_engine/.env 文件中设置：\n"
                "  ANTHROPIC_API_KEY=sk-ant-..."
            )
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        _client = anthropic.Anthropic(**kwargs)
    return _client


def call_llm(system_prompt: str, user_prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """普通文本调用"""
    client = get_client()
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )
    return msg.content[0].text


def call_llm_json(system_prompt: str, user_prompt: str, model: str = "claude-haiku-4-5-20251001") -> dict:
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
