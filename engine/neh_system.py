"""
NEH 子系统：Predictor（预测） + EventPool（存储） + Trigger（触发判定）
宏观叙事事件，每 5 轮预测一次，每轮检查触发条件
"""
from .llm_client import call_llm_json
from .character import DEFAULT_CHARACTER

# ─── Predictor ────────────────────────────────────────────────────────────────

PREDICT_SYSTEM = """你是叙事引擎的【NEH Predictor】模块。
根据当前叙事状态，预测 3-4 个未来可能发生的宏观叙事事件。

输出 JSON 格式：
{
  "events": [
    {
      "id": "唯一ID如neh_001",
      "name": "事件名称（10字内）",
      "description": "事件简述（30字内）",
      "trigger_condition": "触发条件描述",
      "trigger_turn_min": 触发的最早轮次（整数）,
      "trigger_turn_max": 触发的最晚轮次（整数）,
      "required_axes": {"tension": ">60"},
      "priority": 1-5之间的整数（5最高）,
      "narrative_impact": "触发后的叙事影响描述"
    }
  ]
}"""


def predict(state: dict, history: list) -> list:
    axes = state["axes"]
    current_turn = state["meta"]["turn"]

    history_summary = ""
    for h in history[-4:]:
        role = "用户" if h["role"] == "user" else DEFAULT_CHARACTER["name"]
        history_summary += f"{role}：{h['content'][:60]}...\n"

    user_prompt = f"""
【角色】{DEFAULT_CHARACTER['name']}
{DEFAULT_CHARACTER['persona'][:100]}

【当前状态】
- 轮次：{current_turn}  张力：{axes['tension']}  亲密度：{axes['intimacy']}
- 情绪：{axes['emotion']}  信息面纱：{axes['info_veil']}
- 活跃线程：{len(state['threads'])} 个

【近期对话摘要】
{history_summary or "（刚开始）"}

请预测 3-4 个宏观叙事事件，事件应该具有戏剧性和不可逆性。"""

    result = call_llm_json(PREDICT_SYSTEM, user_prompt)
    return result.get("events", [])


# ─── Trigger ─────────────────────────────────────────────────────────────────

TRIGGER_SYSTEM = """你是叙事引擎的【NEH Trigger】模块。
判断当前是否应该触发某个待发事件。

输出 JSON 格式：
{
  "should_trigger": true/false,
  "event_id": "要触发的事件ID，或null",
  "event_name": "事件名称，或null",
  "trigger_reason": "触发/不触发的原因",
  "pending_count": 待触发事件数量
}"""


def check_trigger(state: dict, turn: int, perception: dict) -> dict:
    pending = state["event_pool"]["pending"]
    if not pending:
        return {
            "_module": "neh_trigger",
            "should_trigger": False,
            "event_id": None,
            "event_name": None,
            "trigger_reason": "事件池为空",
            "pending_count": 0,
        }

    axes = state["axes"]
    events_text = "\n".join(
        f"- [{e['id']}] {e['name']}（优先级{e.get('priority',1)}，"
        f"触发区间{e.get('trigger_turn_min',0)}-{e.get('trigger_turn_max',999)}轮，"
        f"条件：{e.get('trigger_condition','')}）"
        for e in pending
    )

    user_prompt = f"""
【当前轮次】第 {turn + 1} 轮
【状态】张力：{axes['tension']}  亲密度：{axes['intimacy']}  情绪：{axes['emotion']}
【用户参与度】{perception.get('engagement_level', 50)}
【本轮叙事机会】{perception.get('narrative_opportunity', '')}

【待触发事件列表】
{events_text}

判断：现在是否是触发某事件的最佳时机？"""

    result = call_llm_json(TRIGGER_SYSTEM, user_prompt)
    result["_module"] = "neh_trigger"
    result["pending_count"] = len(pending)
    return result
