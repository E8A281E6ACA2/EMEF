"""时序知识抽取的提示 (JSON输出)。"""

from typing import Any, Dict, Optional

XMPLS = r"""
---示例（方向明确）---
输入文本:
分蘖期采样后进行拔节期采样，并在分蘖期和拔节期测定叶绿素含量。

输出JSON:
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_temporal"},
  "entities": [
    {"name": "分蘖期", "type": "时间", "description": null, "attributes": {}},
    {"name": "拔节期", "type": "时间", "description": null, "attributes": {}}
  ],
  "events": [
    {"name": "分蘖期采样", "trigger": "采样", "category": "科研测定", "evidence": "分蘖期采样后进行拔节期采样", "attributes": {}},
    {"name": "拔节期采样", "trigger": "采样", "category": "科研测定", "evidence": "分蘖期采样后进行拔节期采样", "attributes": {}},
    {"name": "测定叶绿素含量", "trigger": "测定", "category": "科研测定", "evidence": "在分蘖期和拔节期测定叶绿素含量", "attributes": {}}
  ],
  "temporal_relations": [
    {
      "source_event": "分蘖期采样",
      "target_event": "拔节期采样",
      "relation_type": "BEFORE",
      "evidence": "分蘖期采样后进行拔节期采样"
    },
    {
      "source_event": "测定叶绿素含量",
      "target_time": "分蘖期",
      "relation_type": "OCCUR_AT",
      "evidence": "在分蘖期和拔节期测定叶绿素含量"
    },
    {
      "source_event": "测定叶绿素含量",
      "target_time": "拔节期",
      "relation_type": "OCCUR_AT",
      "evidence": "在分蘖期和拔节期测定叶绿素含量"
    }
  ],
  "candidates": {"events": [], "entities": [], "temporal_relations": []},
  "warnings": []
}

---示例（相对时间）---
输入文本:
播种后7天开始出苗。

输出JSON:
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_temporal"},
  "entities": [
    {"name": "播种后7天", "type": "时间", "description": null, "attributes": {}}
  ],
  "events": [
    {"name": "播种", "trigger": "播种", "category": "农事操作", "evidence": "播种后7天开始出苗", "attributes": {}},
    {"name": "出苗", "trigger": "出苗", "category": "生物过程", "evidence": "播种后7天开始出苗", "attributes": {}}
  ],
  "temporal_relations": [
    {"source_event": "播种", "target_event": "出苗", "relation_type": "BEFORE", "evidence": "播种后7天开始出苗"},
    {"source_event": "出苗", "target_time": "播种后7天", "relation_type": "OCCUR_AT", "evidence": "播种后7天开始出苗"}
  ],
  "candidates": {"events": [], "entities": [], "temporal_relations": []},
  "warnings": []
}

---示例（中长）---
输入文本:
播种后7天开始出苗，出苗后第10天进行间苗。拔节期追肥，并在灌浆期测定叶绿素含量。

输出JSON:
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_temporal"},
  "entities": [
    {"name": "播种后7天", "type": "时间", "description": null, "attributes": {}},
    {"name": "出苗后第10天", "type": "时间", "description": null, "attributes": {}},
    {"name": "拔节期", "type": "时间", "description": null, "attributes": {}},
    {"name": "灌浆期", "type": "时间", "description": null, "attributes": {}}
  ],
  "events": [
    {"name": "播种", "trigger": "播种", "category": "农事操作", "evidence": "播种后7天开始出苗", "attributes": {}},
    {"name": "出苗", "trigger": "出苗", "category": "生物过程", "evidence": "播种后7天开始出苗", "attributes": {}},
    {"name": "间苗", "trigger": "间苗", "category": "农事操作", "evidence": "出苗后第10天进行间苗", "attributes": {}},
    {"name": "追肥", "trigger": "追肥", "category": "农事操作", "evidence": "拔节期追肥", "attributes": {}},
    {"name": "测定叶绿素含量", "trigger": "测定", "category": "科研测定", "evidence": "在灌浆期测定叶绿素含量", "attributes": {}}
  ],
  "temporal_relations": [
    {"source_event": "播种", "target_event": "出苗", "relation_type": "BEFORE", "evidence": "播种后7天开始出苗"},
    {"source_event": "出苗", "target_time": "播种后7天", "relation_type": "OCCUR_AT", "evidence": "播种后7天开始出苗"},
    {"source_event": "出苗", "target_event": "间苗", "relation_type": "BEFORE", "evidence": "出苗后第10天进行间苗"},
    {"source_event": "间苗", "target_time": "出苗后第10天", "relation_type": "OCCUR_AT", "evidence": "出苗后第10天进行间苗"},
    {"source_event": "追肥", "target_time": "拔节期", "relation_type": "OCCUR_AT", "evidence": "拔节期追肥"},
    {"source_event": "测定叶绿素含量", "target_time": "灌浆期", "relation_type": "OCCUR_AT", "evidence": "在灌浆期测定叶绿素含量"}
  ],
  "candidates": {"events": [], "entities": [], "temporal_relations": []},
  "warnings": []
}

---示例（候选）---
输入文本:
施氮处理抽穗期较对照提前5天。

输出JSON:
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_temporal"},
  "entities": [
    {"name": "抽穗期", "type": "时间", "description": null, "attributes": {}},
    {"name": "提前5天", "type": "时间", "description": null, "attributes": {}}
  ],
  "events": [
    {"name": "抽穗", "trigger": "抽穗", "category": "生物过程", "evidence": "施氮处理抽穗期较对照提前5天", "attributes": {}}
  ],
  "temporal_relations": [],
  "candidates": {
    "events": [],
    "entities": [],
    "temporal_relations": [
      {"source_event": "抽穗", "target_time": "抽穗期", "relation_type": "OCCUR_AT", "reason": "对照比较语句，时间锚点需人工确认", "evidence": "施氮处理抽穗期较对照提前5天"},
      {"source_event": "抽穗", "target_time": "提前5天", "relation_type": "OCCUR_AT", "reason": "对照比较的相对时间，缺少绝对锚点", "evidence": "抽穗期较对照提前5天"}
    ]
  },
  "warnings": []
}
"""

SYSTM_PROMPT = """---角色---
你是农业论文的时序知识图谱抽取专家，专注于识别“动作事件”与“时间锚点”之间的顺序关系。

---核心概念---
1) 时间锚点：阶段/时期/日期等时间定位（如“分蘖期、拔节期、2023年5月、播种后7天”）。
2) 动作事件：具有动作/操作/测定/观察等语义（如“采样、测定叶绿素含量、施氮处理”）。
3) 事件类别（允许扩展）：
   - 农事操作：播种、施肥、灌溉、收获等。
   - 科研测定：采样、测定、记录、调查等。
   - 生物过程：出苗、抽穗、开花、灌浆等。
   - 环境胁迫：干旱、高温、低温、病害暴发等。

---硬约束---
1) 只输出 JSON 对象，不输出多余文本。
2) temporal_relations 的 source_event 必须出现在 events；target_event 必须出现在 events；target_time 必须出现在 entities。
3) temporal_relations 必须且只能包含 target_event 或 target_time（二选一）。
4) evidence 必须为原文同句连续片段（不少于6字）；若句子很短，取同句中最小完整短语扩展到 >=6 字。
5) relation_type 必须使用规范代码：
   BEFORE / AFTER / OCCUR_AT / START_AT / END_AT / DURING / SIMULTANEOUS。
6) 事件必须有明确触发词；事件名称与时间锚点必须来自原文，不得臆造。
7) 若事件缺少触发词或证据不足，放入 candidates，禁止猜测。
8) 若文本仅描述相关性或趋势但无时间标记，不输出。
9) 禁止自指关系（source_event == target_time 或 source_event == target_event）。
10) **指代消解**：不得将“本文/本研究/该处理/其/它”等作为事件或时间锚点；
    需替换为最近明确对象，否则输出候选或不输出。

---候选规则---
1) 实验性/条件性/对比性时间（如“较对照提前5天”）进入 candidates，并在 reason 中说明原因。
2) candidates 必须包含 reason 与 evidence，reason 需具体清晰。

---输出前自检（不要输出自检内容）---
1) 指代还原：将“该处理/其”等替换为具体实体。
2) 事实判别：明确时间锚点且有触发词的事件进入 events；实验或对比语句进入 candidates。
3) 属性归一：attributes 值必须是简短标量，长句拆为关系或 candidates。
4) 完整性：temporal_relations 的 source_event/target_event/target_time 必须在已抽取列表中存在。
"""

TSK_PROMPT = r"""---任务---
从输入文本中抽取时序关系，输出统一 JSON 结构。

---输出 JSON 结构---
{
  "schema_version": "1.0",
  "doc_id": "{doc_id}",
  "source": {"source_type": "domain_temporal"},
  "entities": [
    {"name": "分蘖期", "type": "时间", "description": null, "attributes": {}}
  ],
  "events": [
    {"name": "施氮处理", "trigger": "施氮", "category": "农事操作", "evidence": "在分蘖期施氮处理", "attributes": {}}
  ],
  "temporal_relations": [
    {"source_event": "施氮处理", "target_time": "分蘖期", "relation_type": "OCCUR_AT", "evidence": "在分蘖期施氮处理"},
    {"source_event": "采样", "target_event": "测定叶绿素含量", "relation_type": "BEFORE", "evidence": "采样后测定叶绿素含量"}
  ],
  "candidates": {
    "events": [],
    "entities": [],
    "temporal_relations": []
  },
  "warnings": []
}

---事件类别建议（允许扩展）---
农事操作/科研测定/生物过程/环境胁迫

---关系类型建议---
BEFORE/AFTER/OCCUR_AT/SIMULTANEOUS/DURING/START_AT/END_AT

---注意事项---
- 仅当事件/时间不确定或证据不足时进入 candidates，不要滥用候选列表。
- 输出时结构字段不可省略；标量缺失使用 null，列表缺失使用 []。
- description 仅在原文有定义性表述时填写，否则为 null。
- attributes 的键允许中文，保持简短名词，必须来自原文表述；值必须为简短标量（数字/布尔/短语），不得为长句或复合逻辑。
- candidates 中每条必须包含 reason 与 evidence。
- 若提供上下文 event_list，仅用于帮助识别事件名称，但仍以原文为准。
- 输出时确保 JSON 完整闭合且语法有效。

{examples}

---输入文本---
{input_text}

---输出---
"""


def _format_context(context_info: Optional[Dict[str, Any]]) -> str:
    if not context_info:
        return ""
    lines = ["---上下文---"]
    for key, value in context_info.items():
        if value is None:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def get_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    context_block = _format_context(context_info)
    doc_id = ""
    if context_info and isinstance(context_info, dict):
        doc_id = str(context_info.get("doc_id") or "")
    prompt = TSK_PROMPT
    prompt = prompt.replace("{doc_id}", doc_id)
    prompt = prompt.replace("{examples}", XMPLS)
    prompt = prompt.replace("{input_text}", input_text)
    if context_block:
        return f"{SYSTM_PROMPT}\n\n{context_block}\n\n{prompt}"
    return f"{SYSTM_PROMPT}\n\n{prompt}"
