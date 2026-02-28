"""
导演层 — 唯一有状态写权限的模块，输出叙事指令 + state_patch
"""
from .llm_client import call_llm_json
from .character import DEFAULT_CHARACTER

SYSTEM = """你是叙事引擎的【导演层】核心决策模块。
你掌握完整的叙事状态，负责制定本轮的叙事战略。

输出 JSON 格式（严格遵守）：
{
  "narrative_directive": "给表现层的核心叙事指令（50字以内）",
  "tension_technique": "使用的微观张力技术名称（如：信息缺口/情感反转/悬停停顿/欲言又止等）",
  "thread_action": {
    "focus": "本轮重点推进的线程名称",
    "action": "推进/暂停/引入/关闭"
  },
  "state_patch": {
    "axes": {
      "tension": 数字或null（不变则null）,
      "intimacy": 数字或null,
      "emotion": {"label": "新情绪", "intensity": 数字} 或null,
      "energy": 数字或null
    },
    "momentum": {
      "pace": "slow/medium/fast 或null",
      "direction": "escalating/stable/de-escalating 或null"
    },
    "threads_add": [],
    "threads_update": [],
    "patch_summary": "本轮状态变化摘要（20字以内）"
  },
  "neh_trigger_recommendation": "触发/等待",
  "director_note": "导演内心独白（调试用，不给用户看）"
}

注意：state_patch.axes 中 null 表示该字段不变。"""


def direct(perception: dict, neh_output: dict, state: dict, history: list) -> dict:
    axes = state["axes"]
    threads_text = "\n".join(
        f"  - [{t['status']}] {t['name']} ({t.get('progress', 0)}%)"
        for t in state["threads"]
    ) or "  （无活跃线程）"

    neh_text = ""
    if neh_output.get("should_trigger"):
        neh_text = f"⚡ NEH 建议触发事件：{neh_output.get('event_name', '未知')}"
    else:
        neh_text = f"NEH 待触发事件数：{neh_output.get('pending_count', 0)}"

    user_prompt = f"""
【角色】{DEFAULT_CHARACTER['name']}
{DEFAULT_CHARACTER['persona']}

【感知层报告】
- 用户意图：{perception.get('user_intent')}
- 情绪：{perception.get('emotional_tone')}  参与度：{perception.get('engagement_level')}
- 关键信号：{perception.get('key_signals')}
- 叙事机会：{perception.get('narrative_opportunity')}
- 张力建议：{perception.get('tension_hint')}

【当前六轴状态】
- 张力：{axes['tension']}  亲密度：{axes['intimacy']}
- 情绪：{axes['emotion']}  驱动：{axes['drive']}  能量：{axes['energy']}
- 动量：{state['momentum']}

【活跃线程】
{threads_text}

【NEH 系统】
{neh_text}

【当前轮次】第 {state['meta']['turn'] + 1} 轮

请制定本轮叙事战略，输出导演决策 JSON。"""

    result = call_llm_json(SYSTEM, user_prompt)
    result["_module"] = "director_layer"

    # 清理 null 值，避免 apply_patch 错误覆盖
    if "state_patch" in result and "axes" in result["state_patch"]:
        result["state_patch"]["axes"] = {
            k: v for k, v in result["state_patch"]["axes"].items() if v is not None
        }
    if "state_patch" in result and "momentum" in result["state_patch"]:
        result["state_patch"]["momentum"] = {
            k: v for k, v in result["state_patch"]["momentum"].items() if v is not None
        }

    return result
