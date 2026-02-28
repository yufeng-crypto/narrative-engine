"""
叙事引擎 Web 原型 — Flask 后端
"""
import os
import json
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, session

from engine.state_manager import StateManager
from engine import perception_layer, director_layer, performance_layer, neh_system
from engine.character import DEFAULT_CHARACTER

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 内存中存储所有会话（原型用）
SESSIONS: dict[str, dict] = {}


def _get_or_create_session(sid: str) -> dict:
    if sid not in SESSIONS:
        sm = StateManager()
        SESSIONS[sid] = {
            "state_manager": sm,
            "history": [],
            "turn": 0,
            "debug_history": [],
        }
    return SESSIONS[sid]


@app.route("/")
def index():
    return render_template("index.html", character=DEFAULT_CHARACTER)


@app.route("/api/new_session", methods=["POST"])
def new_session():
    sid = str(uuid.uuid4())
    sess = _get_or_create_session(sid)
    return jsonify({"session_id": sid, "state": sess["state_manager"].get_state()})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    sid = data.get("session_id")
    user_msg = data.get("message", "").strip()

    if not sid or sid not in SESSIONS:
        return jsonify({"error": "无效的 session_id，请刷新页面"}), 400
    if not user_msg:
        return jsonify({"error": "消息不能为空"}), 400

    sess = SESSIONS[sid]
    sm: StateManager = sess["state_manager"]
    state = sm.get_state()
    history = sess["history"]
    turn = sess["turn"]

    debug = {}

    # ── 1. 感知层 + NEH Trigger 并发 ──────────────────────
    # Trigger 不依赖感知层，两者可同时发起；感知结果仍完整传给导演层
    def _run_perception():
        try:
            return perception_layer.analyze(user_msg, state, history)
        except Exception as e:
            return {"error": str(e), "_module": "perception_layer"}

    def _run_neh_trigger():
        try:
            return neh_system.check_trigger(state, turn, {})
        except Exception as e:
            return {"error": str(e), "_module": "neh_trigger", "should_trigger": False}

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_perception = executor.submit(_run_perception)
        f_trigger    = executor.submit(_run_neh_trigger)
        perception  = f_perception.result()
        neh_trigger = f_trigger.result()

    debug["perception"] = perception
    debug["neh_trigger"] = neh_trigger

    # 若 NEH 建议触发，执行触发（不可逆）
    neh_fired_event = None
    if neh_trigger.get("should_trigger") and neh_trigger.get("event_id"):
        neh_fired_event = sm.fire_event(neh_trigger["event_id"])
        debug["neh_fired"] = neh_fired_event

    # ── 2. 导演层（写状态）───────────────────────────────
    state = sm.get_state()   # 刷新（NEH 可能已改变事件池）
    try:
        director = director_layer.direct(perception, neh_trigger, state, history)
    except Exception as e:
        director = {"error": str(e), "_module": "director_layer",
                    "narrative_directive": "自然回应用户",
                    "tension_technique": "无",
                    "state_patch": {}}
    debug["director"] = director

    patch = director.get("state_patch", {})
    sm.apply_patch(patch)
    state = sm.get_state()

    # ── 3. 表现层 ─────────────────────────────────────────
    try:
        performance = performance_layer.generate(director, state, history)
    except Exception as e:
        performance = {"error": str(e), "_module": "performance_layer",
                       "response": "（系统错误，无法生成回复）"}
    debug["performance"] = performance

    response_text = performance.get("response", "")

    # ── 更新会话 ──────────────────────────────────────────
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": response_text})
    sess["turn"] += 1
    sess["debug_history"].append({"turn": turn + 1, "debug": debug})

    # ── 4. NEH Predictor 后台执行（每 5 轮，不阻塞响应）──
    # 预测结果写入事件池，仅影响后续轮次，当前响应无需等待
    debug["neh_predict"] = "background"
    if turn % 5 == 0:
        history_snap = list(history)
        state_snap   = sm.get_state()

        def _bg_predict():
            try:
                new_events = neh_system.predict(state_snap, history_snap)
                sm.update_event_pool(new_events)
            except Exception:
                pass

        threading.Thread(target=_bg_predict, daemon=True).start()

    return jsonify({
        "response": response_text,
        "state": sm.get_state(),
        "debug": debug,
        "turn": sess["turn"],
    })


@app.route("/api/state/<sid>")
def get_state(sid: str):
    if sid not in SESSIONS:
        return jsonify({"error": "not found"}), 404
    return jsonify(SESSIONS[sid]["state_manager"].get_state())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n🎭 叙事引擎原型启动 → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
