# EviSI-Eval v0.7 — 架构方案

> 状态：设计阶段  
> 日期：2026-07-01

## 0. 核心思路

**Source + Reference 一起看、一起抽、一起冻结 = 评测基准联合卡。**

当前 v0.6 问题：
- Source 先独立抽取 → 漏了 "load balancing" 这种关键概念
- Reference 再被动投影到 Source items → Reference 不能帮助发现 Source 的漏抽
- JSON 太深（三层 projection + component_results + operators 五字段 + hard_requirement 六字段）
- 16 phases，调用多，prompt 重

v0.7 模型：

```
Source ──┐
         ├─ 联合抽取 (LLM 同时看，按 segment 对齐) ──→ 联合卡冻结 ──→ SI 匹配 ──→ 打分
Reference┘
```

**对齐靠数组位置。** Source anchors = [a, b, c]，Reference = [1, 2, 3]，SI = [甲, 乙, 丙]。位置即对应关系。

**断句和抽取拆开。** 断句/对齐是纯文本操作，Anchor/Event/Relation 抽取是语义操作——分开后每次调用更聚焦、token 更省、缓存粒度更细。

---

## 1. 完整 Phase 结构

### 1.1 联合卡构建（每个 sample 一次，8 次 LLM 调用）

```
Source 侧（只看源文，4 次调用）
─────────────────────────────────────
Step 1   断句                   v07_source_segment
        输入：source_text
        输出：source_segments [{seg_id, source_text}]

Step 2   Anchor 抽取            v07_source_anchor
        输入：source_segments
        输出：source_anchors [{anchor_id, seg_id, type, text, evidence, importance}]

Step 3   Event 抽取             v07_source_event
        输入：source_segments
        输出：source_events [{event_id, seg_id, type, summary, evidence, importance}]

Step 4   Relation 抽取          v07_source_relation
        输入：source_segments + source_events
        输出：source_relations [{relation_id, type, summary, evidence, source_event_ids, importance}]

Reference 侧（对齐到 Source，4 次调用）
─────────────────────────────────────
Step 5   对齐断句               v07_reference_align
        输入：source_segments + reference_translation
        输出：reference_segments [{seg_id, reference_text}]
        （数量与 source_segments 相同，顺序对齐）

Step 6   Anchor 对齐            v07_reference_anchor
        输入：source_segments + source_anchors + reference_segments + reference_translation
        输出：reference_anchors [{anchor_id, seg_id, text, evidence}]
        （数量/顺序与 source_anchors 完全一致）

Step 7   Event 对齐             v07_reference_event
        输入：source_segments + source_events + reference_segments + reference_translation
        输出：reference_events [{event_id, seg_id, summary, evidence}]
        （数量/顺序与 source_events 完全一致）

Step 8   Relation 对齐          v07_reference_relation
        输入：source_relations + reference_events + reference_translation
        输出：reference_relations [{relation_id, preserved, summary}]
        （数量/顺序与 source_relations 完全一致）

        → Python 合并为 Joint Card，计算 joint_card_hash，冻结
```

### 1.2 SI 评测（每个同传系统，6 次 LLM 调用）

```
Step 9   SI 对齐断句            v07_si_align
        输入：source_segments + si_translation
        输出：si_segments [{seg_id, si_text}]
        （数量与 source_segments 相同）

Step 10  SI Anchor 匹配         v07_si_anchor_match
        输入：source_segments + joint_anchors + si_segments + si_translation
        输出：anchor_matches [{anchor_id, match, si_text, si_evidence, brief}]
        （数量/顺序与 joint_anchors 完全一致）

Step 11  SI Event 匹配          v07_si_event_match
        输入：source_events + joint_events + si_segments + si_translation
        输出：event_matches [{event_id, match, si_summary, si_evidence, brief}]
        （数量/顺序与 joint_events 完全一致）

Step 12  SI Relation 匹配       v07_si_relation_match
        输入：source_relations + joint_relations + si_event_matches + si_translation
        输出：relation_matches [{relation_id, match, si_evidence, brief}]
        （数量/顺序与 joint_relations 完全一致）
        依赖处理：端点 Event 全部 missing/contradiction → not_scored

Step 13  Fluency                 （复用 v0.5）
Step 14  SI Expression           （复用 v0.5）

        → Python 确定性打分
```

### 1.3 调用次数对比

| | v0.6 | v0.7 |
|---|---|---|
| 联合卡构建 | 9（Source 4 + Reference 4 + Context 1） | **8**（Source 4 + Reference 4） |
| 每个 SI 系统 | 7（对齐+投影×3+Fluency+Expression） | **6**（对齐+匹配×3+Fluency+Expression） |
| 单系统总计 | 16 | **14** |
| JSON 字段（一条 Anchor） | ~25 | **7**（联合卡）+ **5**（SI match） |
| Prompt 总数 | 14（含 protocol 注入） | **12**（全部自包含，无 protocol） |

---

## 2. Prompt 文件夹结构

```
prompts/
├── source/                     # 只看源文
│   ├── v07_source_segment.md   # Step 1  断句
│   ├── v07_source_anchor.md    # Step 2  Anchor 抽取
│   ├── v07_source_event.md     # Step 3  Event 抽取
│   └── v07_source_relation.md  # Step 4  Relation 抽取
│
├── reference/                  # 对齐到 source，输出 reference 侧
│   ├── v07_reference_align.md  # Step 5  对齐断句
│   ├── v07_reference_anchor.md # Step 6  Anchor 对齐
│   ├── v07_reference_event.md  # Step 7  Event 对齐
│   └── v07_reference_relation.md # Step 8 Relation 对齐
│
└── si/                         # 匹配联合卡，输出 match 判断
    ├── v07_si_align.md         # Step 9  SI 对齐断句
    ├── v07_si_anchor_match.md  # Step 10 SI Anchor 匹配
    ├── v07_si_event_match.md   # Step 11 SI Event 匹配
    └── v07_si_relation_match.md # Step 12 SI Relation 匹配
```

Source/Reference/SI 三组的 prompt 结构高度相似，差异只在：
- **前置输入**：Source 只看源文；Reference 看 source 输出 + 译文；SI 看联合卡 + 同传
- **输出内容**：Source 输出抽取结果；Reference 输出对齐表达；SI 输出 match 判断

---

## 3. 数据流

Source 和 Reference 各自输出展平列表（带 seg_id），代码按位置 zip 合并：

```
source_anchors:               reference_anchors:          Joint Card:
──────────────────────        ──────────────────────      ──────────────────────
[0] {S1_A1, S1, term, ...}   [0] {S1_A1, S1, "轮询...")  [0] {S1_A1, term,
[1] {S2_A1, S2, term, ...}   [1] {S2_A1, S2, "负载...")       source:..., ref:...}
[2] {S2_A2, S2, entity,...}  [2] {S2_A2, S2, "马克")      [1] ...
                              （位置对齐，数量相等）            （代码 zip 合并）
```

Events、Relations 同理。代码校验：
- source_anchors.length == reference_anchors.length
- source_events.length == reference_events.length
- source_relations.length == reference_relations.length
- 每条对应的 anchor_id / event_id / relation_id 一致

---

## 4. 关键设计决策

| # | 决策 | 理由 |
|---|---|---|
| 1 | 无独立 Protocol 文件 | 12 个 prompt 全部自包含 |
| 2 | 断句与抽取拆开 | 任务更聚焦、缓存粒度更细、token 更省 |
| 3 | 对齐靠数组位置 | 不需要 projection_id 交叉引用 |
| 4 | Event 只保留 6 字段 | summary 用自然语言承载全部语义 |
| 5 | Anchor 只保留 6 字段 | text + evidence 并列，无需 component_results |
| 6 | Source 是唯一语义权威 | SI ≠ Reference 不自动判错 |
| 7 | 断句 ~2 句粒度 | Step 1 完成，后续全部复用 |
| 8 | 三文件夹组织 | source/reference/si 各 4 个 prompt，结构清晰可审查 |

## 5. 后续迭代方向（不在本版本）

- 三组 prompt 可抽象为统一模板 + 差异化前置字段
- 维度权重待人工标注校准
- partial 值（0.5）待校准
- 多模型一致性实验
