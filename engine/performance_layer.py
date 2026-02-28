"""
表现层 — 依据导演指令生成最终角色回复（用更强的模型）
"""
from .llm_client import call_llm
from .character import DEFAULT_CHARACTER

SYSTEM_TPL = """你是 {name}。

【角色设定】
{persona}

【说话风格】
{speech_style}

【导演本轮指令】
{directive}

【张力技术】
使用技术：{tension_technique}

【状态感知】
当前张力：{tension}  亲密度：{intimacy}  情绪：{emotion}

规则：
- 直接输出角色的话，不加引号，不加 {name}：前缀
- 禁止解释技术或跳出角色
- 回复长度 2-6 句话，保持节奏感
- 用空行分段制造停顿感"""


def generate(director_output: dict, state: dict, history: list) -> dict:
    directive = director_output.get("narrative_directive", "自然推进对话")
    technique = director_output.get("tension_technique", "自然流")
    axes = state["axes"]

    system = SYSTEM_TPL.format(
        name=DEFAULT_CHARACTER["name"],
        persona=DEFAULT_CHARACTER["persona"],
        speech_style=DEFAULT_CHARACTER["speech_style"],
        directive=directive,
        tension_technique=technique,
        tension=axes["tension"],
        intimacy=axes["intimacy"],
        emotion=axes["emotion"],
    )

    history_text = ""
    for h in history[-8:]:
        role = "用户" if h["role"] == "user" else DEFAULT_CHARACTER["name"]
        history_text += f"{role}：{h['content']}\n"

    user_prompt = f"""【近期对话记录】
{history_text if history_text else "（对话开始）"}

请以 {DEFAULT_CHARACTER['name']} 的身份，按照导演指令生成本轮回复。"""

    response_text = call_llm(system, user_prompt)

    return {
        "_module": "performance_layer",
        "response": response_text,
        "directive_applied": directive,
        "technique_used": technique,
    }
