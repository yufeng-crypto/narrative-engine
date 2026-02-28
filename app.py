"""
叙事引擎 Web 原型 — Flask 后端
"""
import os
import sys
import json
import uuid
import logging
import logging.handlers
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, session

from engine.state_manager import StateManager
from engine import perception_layer, director_layer, performance_layer, neh_system
from engine.character import DEFAULT_CHARACTER


# ── 日志配置 ──────────────────────────────────────────────────────────────────
def _setup_logging():
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件：DEBUG 全量，最大 5MB，保留 3 个备份
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # 控制台：只显示 INFO 及以上
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root.addHandler(fh)
    root.addHandler(ch)
    return log_path


LOG_PATH = _setup_logging()
log = logging.getLogger("narrative_engine.app")

# ── 启动信息 ──────────────────────────────────────────────────────────────────
log.info("=" * 60)
log.info("叙事引擎启动")
log.info("Python: %s", sys.version)
log.info("日志文件: %s", LOG_PATH)
log.info("=" * 60)

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
    log.info("新会话创建: %s", sid)
    return jsonify({"session_id": sid, "state": sess["state_manager"].get_state()})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    sid = data.get("session_id")
    user_msg = data.get("message", "").strip()

    if not sid or sid not in SESSIONS:
        log.warning("无效 session_id: %s", sid)
        return jsonify({"error": "无效的 session_id，请刷新页面"}), 400
    if not user_msg:
        return jsonify({"error": "消息不能为空"}), 400

    sess = SESSIONS[sid]
    sm: StateManager = sess["state_manager"]
    state = sm.get_state()
    history = sess["history"]
    turn = sess["turn"]

    log.info("▶ Turn %d | sid=%s | 用户: %s", turn + 1, sid[:8], user_msg[:80])
    log.debug("  当前状态: %s", json.dumps(state, ensure_ascii=False))

    debug = {}

    # ── 1. 感知层 + NEH Trigger 并发 ──────────────────────
    def _run_perception():
        try:
            log.debug("  [感知层] 开始分析...")
            result = perception_layer.analyze(user_msg, state, history)
            log.debug("  [感知层] 结果: %s", json.dumps(result, ensure_ascii=False))
            return result
        except Exception as e:
            log.error("  [感知层] 异常: %s\n%s", e, traceback.format_exc())
            return {"error": str(e), "_module": "perception_layer"}

    def _run_neh_trigger():
        try:
            log.debug("  [NEH Trigger] 开始检查...")
            result = neh_system.check_trigger(state, turn, {})
            log.debug("  [NEH Trigger] 结果: %s", json.dumps(result, ensure_ascii=False))
            return result
        except Exception as e:
            log.error("  [NEH Trigger] 异常: %s\n%s", e, traceback.format_exc())
            return {"error": str(e), "_module": "neh_trigger", "should_trigger": False}

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_perception = executor.submit(_run_perception)
        f_trigger    = executor.submit(_run_neh_trigger)
        perception  = f_perception.result()
        neh_trigger = f_trigger.result()

    debug["perception"] = perception
    debug["neh_trigger"] = neh_trigger

    # 若 NEH 建议触发，执行触发
    neh_fired_event = None
    if neh_trigger.get("should_trigger") and neh_trigger.get("event_id"):
        neh_fired_event = sm.fire_event(neh_trigger["event_id"])
        debug["neh_fired"] = neh_fired_event
        log.info("  [NEH] 触发事件: %s -> %s", neh_trigger.get("event_id"), neh_fired_event)

    # ── 2. 导演层（写状态）───────────────────────────────
    state = sm.get_state()
    log.debug("  [导演层] 开始...")
    try:
        director = director_layer.direct(perception, neh_trigger, state, history)
        log.debug("  [导演层] 结果: %s", json.dumps(director, ensure_ascii=False))
    except Exception as e:
        log.error("  [导演层] 异常: %s\n%s", e, traceback.format_exc())
        director = {"error": str(e), "_module": "director_layer",
                    "narrative_directive": "自然回应用户",
                    "tension_technique": "无",
                    "state_patch": {}}
    debug["director"] = director

    patch = director.get("state_patch", {})
    if patch:
        log.debug("  [状态] 应用 patch: %s", json.dumps(patch, ensure_ascii=False))
    sm.apply_patch(patch)
    state = sm.get_state()

    # ── 3. 表现层 ─────────────────────────────────────────
    log.debug("  [表现层] 开始生成...")
    try:
        performance = performance_layer.generate(director, state, history)
        log.debug("  [表现层] 结果: %s", json.dumps(performance, ensure_ascii=False))
    except Exception as e:
        log.error("  [表现层] 异常: %s\n%s", e, traceback.format_exc())
        performance = {"error": str(e), "_module": "performance_layer",
                       "response": "（系统错误，无法生成回复）"}
    debug["performance"] = performance

    response_text = performance.get("response", "")
    log.info("◀ Turn %d 完成 | 回复: %s", turn + 1, response_text[:80])

    # ── 更新会话 ──────────────────────────────────────────
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": response_text})
    sess["turn"] += 1
    sess["debug_history"].append({"turn": turn + 1, "debug": debug})

    # ── 4. NEH Predictor 后台执行（每 5 轮）──────────────
    debug["neh_predict"] = "background"
    if turn % 5 == 0:
        history_snap = list(history)
        state_snap   = sm.get_state()

        def _bg_predict():
            try:
                log.debug("  [NEH Predict] 后台开始...")
                new_events = neh_system.predict(state_snap, history_snap)
                sm.update_event_pool(new_events)
                log.debug("  [NEH Predict] 完成，新事件数: %d", len(new_events) if new_events else 0)
            except Exception as e:
                log.error("  [NEH Predict] 后台异常: %s\n%s", e, traceback.format_exc())

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
    log.info("启动 Flask，端口 %d", port)
    print(f"\n叙事引擎原型启动 -> http://localhost:{port}")
    print(f"日志文件: {LOG_PATH}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
