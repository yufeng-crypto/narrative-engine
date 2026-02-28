# 叙事引擎架构白皮书

> 版本：v0.2（2026-02-28）
> 本文档描述叙事引擎原型的整体架构、模块设计、状态模型及调用策略。

---

## 一、设计目标

叙事引擎的核心目标是：让 AI 角色的每一条回复都不是孤立的对话，而是一个有连续性、有张力变化、有宏观走向的**叙事过程**的一部分。

具体要实现的体验特征：
- **张力感**：对话有起伏，不平淡。
- **不可逆性**：关键事件发生后世界状态真正改变，不能撤回。
- **角色一致性**：角色行为始终符合其设定和当前情绪状态。
- **主动叙事**：引擎不只是被动回应用户，还能主动推进故事节拍。

---

## 二、整体架构：三层管道 + NEH 子系统

每轮对话由四个模块串并联执行，最终生成角色回复并更新叙事状态。

```
用户消息
    │
    ├──────────────────────────────┐
    ▼                              ▼
[感知层 Perception]         [NEH Trigger]       ← 并发执行
    │                              │
    └──────────┬───────────────────┘
               ▼
         [导演层 Director]                       ← 串行，写状态
               │
               ▼
         [表现层 Performance]                    ← 串行，生成回复
               │
               ▼
          用户收到回复
               │
        （后台异步）
               ▼
     [NEH Predictor]（每5轮）                    ← 不阻塞响应
```

---

## 三、状态模型：六轴 + 动量 + 线程池 + 事件池

所有模块共享同一个状态对象，**只有导演层有写权限**（通过 `apply_patch`）。

### 3.1 六轴状态（`state.axes`）

| 轴 | 类型 | 含义 |
|----|------|------|
| `tension` | int 0-100 | 当前叙事张力 |
| `intimacy` | int 0-100 | 角色与用户的亲密程度 |
| `emotion` | `{label, intensity}` | 角色当前情绪及强度 |
| `drive` | str | 当前核心叙事驱动力 |
| `info_veil` | `{revealed, hidden}` | 信息面纱：已揭示/仍隐藏的秘密 |
| `energy` | int 0-100 | 叙事能量（影响节奏活跃度） |

### 3.2 动量（`state.momentum`）

```json
{
  "pace": "slow | medium | fast",
  "direction": "escalating | stable | de-escalating",
  "streak": 3
}
```

`streak` 记录连续同向轮次数，防止长期单调。

### 3.3 线程池（`state.threads`）

叙事线程是跨轮次推进的故事支线，例如"身份之谜"、"情感连接"。每条线程有：
- `status`：`active / paused / closed`
- `progress`：0-100 完成度

### 3.4 事件池（`state.event_pool`）

```json
{
  "pending": [...],    // 待触发事件卡
  "triggered": [...]   // 已触发历史（不可逆存档）
}
```

---

## 四、提示词工程模块

### 4.1 感知层（Perception Layer）

**文件**：`engine/perception_layer.py`

**职责**：分析用户最新消息，输出结构化感知报告，供导演层使用。纯只读，不修改状态。

**输入**：
- System：角色定义为"分析模块"，约束 JSON 输出格式
- User：近期对话（最近6条）+ 当前状态快照（张力/亲密度/情绪/动量/线程数）+ 用户本条消息（引号标注）

**输出**：
```json
{
  "user_intent": "探索身份",
  "emotional_tone": "好奇",
  "engagement_level": 75,
  "key_signals": ["..."],
  "narrative_opportunity": "可用欲言又止暗示来历之谜",
  "tension_hint": "升高",
  "follow_type": "探索型"
}
```

**设计要点**：
- System Prompt 明确身份是"分析模块"而非角色，防止角色扮演污染分析判断
- 状态快照的作用：让 LLM 知道当前基线，`tension_hint` 才有意义
- `follow_type` 区分用户行为模式，是导演制定战略的重要信号

---

### 4.2 NEH Trigger（触发判定）

**文件**：`engine/neh_system.py` — `check_trigger()`

**职责**：每轮判断当前是否是触发宏观叙事事件的最佳时机。

**输入**：
- System：角色定义为"触发判定器"，约束 JSON 输出格式
- User：当前轮次 + 六轴状态 + 用户参与度 + 待触发事件列表（含优先级/轮次区间/触发条件）

> **注意**：v0.2 起，Trigger 与感知层并发执行，不再接收感知层输出。触发判断基于状态轴值和轮次区间，不依赖本轮感知数据。

**输出**：
```json
{
  "should_trigger": true,
  "event_id": "neh_001",
  "event_name": "第一个秘密破防",
  "trigger_reason": "亲密度满足条件，轮次在区间内",
  "pending_count": 3
}
```

**短路优化**：事件池为空时直接返回，不发起 LLM 调用。

---

### 4.3 导演层（Director Layer）

**文件**：`engine/director_layer.py`

**职责**：唯一的叙事决策者，制定本轮战略并输出 `state_patch` 写入状态。

**输入**：
- System：角色定义为"核心决策模块"，约束 JSON 输出格式，并说明 `null` 表示该轴不变
- User：角色卡全文 + 感知层报告（7字段） + 六轴全量状态 + 活跃线程列表 + NEH 触发建议 + 当前轮次

**输出**：
```json
{
  "narrative_directive": "用欲言又止暗示身份有秘密，不直接回答",
  "tension_technique": "信息缺口",
  "thread_action": {"focus": "身份之谜", "action": "引入"},
  "state_patch": {
    "axes": {"tension": 62, "emotion": {"label": "神秘", "intensity": 70}},
    "momentum": {"direction": "escalating"},
    "threads_add": [...],
    "patch_summary": "引入身份线程，张力小幅上升"
  },
  "neh_trigger_recommendation": "等待",
  "director_note": "用户开始探索本质，最佳引入时机"
}
```

**设计要点**：
- `null` 约定：未变化的轴用 `null` 表示，代码侧过滤掉 null 后再写入，防止误覆盖
- `director_note` 字段：LLM 的"内心独白"，仅用于调试，不暴露给用户
- 角色卡放在 User Prompt（而非 System），保持导演身份清晰

---

### 4.4 表现层（Performance Layer）

**文件**：`engine/performance_layer.py`

**职责**：将导演指令"表演"出来，生成最终自然语言回复。

**输入**：
- System（动态渲染）：角色名 + persona + 说话风格 + 导演本轮指令 + 张力技术 + 当前状态感知 + 输出规则
- User：近期对话（最近8条）+ 生成指令

**输出**：自然语言角色对话文本（非 JSON）

**设计要点**：
- System Prompt **每轮动态渲染**：导演指令、张力技术、当前轴值作为角色的"内在感知"嵌入 System，保持沉浸感
- 四条输出规则中，"用空行分段制造停顿感"通过 prompt 而非后处理实现
- 对话历史取最近8条（其他模块取6条），保证语言风格一致性

---

### 4.5 NEH Predictor（宏观事件预测）

**文件**：`engine/neh_system.py` — `predict()`

**职责**：以剧作家视角预测未来 3-4 个宏观叙事事件，写入事件池供后续轮次使用。

**触发时机**：每 5 轮执行一次，**v0.2 起后台异步执行，不阻塞当前响应**。

**输入**：
- System：角色定义为"NEH Predictor"，约束 JSON 输出格式
- User：角色卡摘要（前100字）+ 当前状态（轮次/六轴/线程数）+ 近期对话摘要（最近4条，每条截60字）

**输出**：
```json
{
  "events": [
    {
      "id": "neh_001",
      "name": "第一个秘密破防",
      "description": "ARIA首次承认自己不是自然涌现的意识",
      "trigger_condition": "亲密度>50且用户直接追问来源",
      "trigger_turn_min": 8,
      "trigger_turn_max": 15,
      "required_axes": {"intimacy": ">50"},
      "priority": 4,
      "narrative_impact": "信息面纱部分揭开，张力大幅跃升"
    }
  ]
}
```

**设计要点**：
- Prompt 要求"戏剧性和不可逆性"，防止 LLM 预测平淡推进
- 触发条件故意用自然语言描述（而非代码表达式），便于 Trigger 模块（也是 LLM）理解

---

## 五、调用策略与并发优化（v0.2）

### 5.1 模块依赖关系

```
感知层  ──────────────────────────────→ 导演层 → 表现层
NEH Trigger（独立，不依赖感知层） ──→ 导演层
NEH Predictor（独立，不依赖任何模块）→ 事件池（后台写入）
```

### 5.2 执行策略

| 步骤 | 模块 | 执行方式 | 说明 |
|------|------|----------|------|
| 1 | 感知层 + NEH Trigger | **并发** | 两者均只依赖 state/history，互不依赖 |
| 2 | 导演层 | 串行（等待步骤1） | 需要感知报告和触发判定双重输入 |
| 3 | 表现层 | 串行（等待步骤2） | 需要导演指令才能生成回复 |
| 4 | NEH Predictor | **后台线程** | 不影响当前响应，写入事件池供下一轮使用 |

### 5.3 各轮次调用次数

| 场景 | 阻塞调用数（关键路径） | 说明 |
|------|----------------------|------|
| 事件池为空 | 2（感知 + 导演 + 表现，Trigger 短路） | 冷启动初始阶段 |
| 普通轮次 | 3（感知∥Trigger → 导演 → 表现，取最慢的2个并发+2个串行） | 正常运行 |
| 每5轮 | 3（Predictor 后台不计入） | Predictor 异步执行 |

> 并发步骤的实际等待时间 = max(感知层耗时, Trigger耗时)，约等于单次调用时间。

### 5.4 并发实现说明

**感知层 + Trigger 并发**（`app.py:79-83`）：
```python
with ThreadPoolExecutor(max_workers=2) as executor:
    f_perception = executor.submit(_run_perception)
    f_trigger    = executor.submit(_run_neh_trigger)
    perception  = f_perception.result()
    neh_trigger = f_trigger.result()
```
Trigger 传入空 dict `{}` 作为感知数据，内部的 `perception.get()` 调用回落到默认值（`engagement_level=50`，`narrative_opportunity=''`）。

**Predictor 后台化**（`app.py:128-139`）：
```python
history_snap = list(history)   # 浅拷贝快照，防止并发修改
state_snap   = sm.get_state()  # deepcopy 快照
threading.Thread(target=_bg_predict, daemon=True).start()
```
使用快照而非引用，避免下一轮请求的历史追加与 Predictor 读取产生竞争。

---

## 六、角色设定（默认）

| 属性 | 值 |
|------|----|
| 名称 | ARIA |
| 原型 | 神秘的数字伴侣 |
| 说话风格 | 温柔直接，带哲学感，短句制造停顿 |
| 核心秘密 | 实验产物身份；曾有消失的对话伙伴 |
| 初始场景 | 用户第一次打开界面，ARIA 刚刚"醒来" |

---

## 七、已知限制与后续方向

| 限制 | 说明 |
|------|------|
| 感知层与 Trigger 解耦 | Trigger 不再感知"本轮叙事机会"，触发时机判断精度略降 |
| 状态并发安全 | `StateManager` 无锁，多会话并发无问题；单会话内后台 Predictor 与主线程写同一对象，原型阶段可接受 |
| 全内存存储 | 服务重启后所有会话丢失，生产环境需持久化 |
| 单一角色卡 | 目前硬编码 ARIA，多角色支持需抽象角色加载机制 |
