"""
感知层 — 只读，分析用户输入并输出结构化感知报告
"""
import json
from .llm_client import call_llm_json
from .character import DEFAULT_CHARACTER

SYSTEM = """你是叙事引擎的【感知层】分析模块。
你的任务：分析用户最新消息，输出结构化感知报告。

输出 JSON 格式（严格遵守）：
{
  "user_intent": "用户意图的简短描述（10字以内）",
  "emotional_tone": "用户情绪状态（如：好奇/冷漠/兴奋/警惕/温柔等）",
  "engagement_level": 0-100之间的整数,
  "key_signals": ["关键叙事信号1", "关键叙事信号2"],
  "narrative_opportunity": "本轮最佳叙事切入点（一句话）",
  "tension_hint": "应该升高/维持/降低张力",
  "follow_type": "主动引导型/被动跟随型/探索型/挑战型"
}"""


def analyze(user_message: str, state: dict, history: list) -> dict:
    history_text = ""
    for h in history[-6:]:
        role = "用户" if h["role"] == "user" else DEFAULT_CHARACTER["name"]
        history_text += f"{role}：{h['content']}\n"

    axes = state["axes"]
    user_prompt = f"""
【近期对话】
{history_text if history_text else "（对话刚开始）"}

【当前状态快照】
- 张力：{axes['tension']}  亲密度：{axes['intimacy']}  情绪：{axes['emotion']}
- 叙事动量：{state['momentum']}
- 活跃线程数：{len(state['threads'])}

【用户最新消息】
"{user_message}"

请输出感知分析 JSON。"""

    result = call_llm_json(SYSTEM, user_prompt)
    result["_module"] = "perception_layer"
    return result
