"""
Session State Manager — 叙事引擎状态枢纽
只有 DirectorLayer 有写权限（通过 apply_patch）
其余模块只读
"""
import copy
import time


DEFAULT_STATE = {
    # ── 六轴状态 ──────────────────────────────────────────
    "axes": {
        "tension":   50,   # 张力 0-100
        "intimacy":  20,   # 亲密度 0-100
        "emotion":   {"label": "平静", "intensity": 40},
        "drive":     "探索与连接",   # 当前核心驱动
        "info_veil": {"revealed": [], "hidden": ["origin_secret", "true_purpose"]},
        "energy":    60,   # 叙事能量 0-100
    },
    # ── 动量 ─────────────────────────────────────────────
    "momentum": {
        "pace":       "medium",   # slow / medium / fast
        "direction":  "stable",   # escalating / stable / de-escalating
        "streak":     0,          # 连续同向轮次数
    },
    # ── 线程池 ───────────────────────────────────────────
    "threads": [],   # [{id, name, status, progress, hooks}]
    # ── NEH 事件池 ───────────────────────────────────────
    "event_pool": {
        "pending":   [],   # 待触发事件卡
        "triggered": [],   # 已触发事件历史
    },
    # ── 元数据 ───────────────────────────────────────────
    "meta": {
        "turn": 0,
        "last_patch_summary": "",
        "created_at": None,
    }
}


class StateManager:
    def __init__(self):
        self._state = copy.deepcopy(DEFAULT_STATE)
        self._state["meta"]["created_at"] = time.time()

    def get_state(self) -> dict:
        """只读快照"""
        return copy.deepcopy(self._state)

    def apply_patch(self, patch: dict):
        """
        Director 专用写入口。
        patch 格式:
        {
          "axes": {...},          # 仅需包含要改变的字段
          "momentum": {...},
          "threads_add": [...],
          "threads_update": [...],   # [{id, status, progress}]
          "patch_summary": "..."
        }
        """
        axes_patch = patch.get("axes", {})
        for k, v in axes_patch.items():
            if k in self._state["axes"]:
                if isinstance(self._state["axes"][k], dict) and isinstance(v, dict):
                    self._state["axes"][k].update(v)
                else:
                    self._state["axes"][k] = v

        mom_patch = patch.get("momentum", {})
        self._state["momentum"].update(mom_patch)

        for t in patch.get("threads_add", []):
            self._state["threads"].append(t)

        updates = {u["id"]: u for u in patch.get("threads_update", [])}
        for t in self._state["threads"]:
            if t["id"] in updates:
                t.update(updates[t["id"]])

        self._state["meta"]["last_patch_summary"] = patch.get("patch_summary", "")
        self._state["meta"]["turn"] += 1

    def update_event_pool(self, events: list):
        """NEH Predictor 写入新事件卡"""
        existing_ids = {e["id"] for e in self._state["event_pool"]["pending"]}
        for ev in events:
            if ev["id"] not in existing_ids:
                self._state["event_pool"]["pending"].append(ev)

    def fire_event(self, event_id: str):
        """NEH Trigger 触发事件（不可逆）"""
        pending = self._state["event_pool"]["pending"]
        for i, ev in enumerate(pending):
            if ev["id"] == event_id:
                ev["fired_at_turn"] = self._state["meta"]["turn"]
                self._state["event_pool"]["triggered"].append(ev)
                pending.pop(i)
                return ev
        return None
