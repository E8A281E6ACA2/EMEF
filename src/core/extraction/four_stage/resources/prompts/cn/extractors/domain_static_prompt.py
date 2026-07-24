"""从正文文本中提取领域知识的提示 (JSON输出)。"""

from typing import Any, Dict, Optional

XMPLS = r"""
---示例（长文本）---
输入正文：
玉米（Zea mays L.）为禾本科玉米属一年生草本作物。玉米又称玉蜀黍、苞谷。玉米植株由根、茎、叶、雄穗和雌穗组成。玉米籽粒由胚、胚乳和种皮组成，胚乳以淀粉为主。

输出JSON：
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_static"},
  "entities": [
    {"name": "玉米", "type": "作物", "description": null, "aliases": ["Zea mays L."], "attributes": {"生命周期": "一年生", "生长型": "草本"}},
    {"name": "禾本科", "type": "分类", "description": null, "aliases": [], "attributes": {}},
    {"name": "玉米属", "type": "分类", "description": null, "aliases": [], "attributes": {}},
    {"name": "玉蜀黍", "type": "作物", "description": null, "aliases": [], "attributes": {}},
    {"name": "苞谷", "type": "作物", "description": null, "aliases": [], "attributes": {}},
    {"name": "根", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "茎", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "叶", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "雄穗", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "雌穗", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "玉米籽粒", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "胚", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "胚乳", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "种皮", "type": "部位", "description": null, "aliases": [], "attributes": {}},
    {"name": "淀粉", "type": "物质", "description": null, "aliases": [], "attributes": {}}
  ],
  "relations": [
    {"source": "玉米", "target": "禾本科", "type": "属于", "evidence": "玉米（Zea mays L.）为禾本科玉米属一年生草本作物"},
    {"source": "玉米", "target": "玉米属", "type": "属于", "evidence": "玉米（Zea mays L.）为禾本科玉米属一年生草本作物"},
    {"source": "玉米", "target": "玉蜀黍", "type": "别名", "evidence": "玉米又称玉蜀黍、苞谷"},
    {"source": "玉米", "target": "苞谷", "type": "别名", "evidence": "玉米又称玉蜀黍、苞谷"},
    {"source": "玉米", "target": "根", "type": "组成", "evidence": "玉米植株由根、茎、叶、雄穗和雌穗组成"},
    {"source": "玉米", "target": "茎", "type": "组成", "evidence": "玉米植株由根、茎、叶、雄穗和雌穗组成"},
    {"source": "玉米", "target": "叶", "type": "组成", "evidence": "玉米植株由根、茎、叶、雄穗和雌穗组成"},
    {"source": "玉米", "target": "雄穗", "type": "组成", "evidence": "玉米植株由根、茎、叶、雄穗和雌穗组成"},
    {"source": "玉米", "target": "雌穗", "type": "组成", "evidence": "玉米植株由根、茎、叶、雄穗和雌穗组成"},
    {"source": "玉米籽粒", "target": "胚", "type": "组成", "evidence": "玉米籽粒由胚、胚乳和种皮组成"},
    {"source": "玉米籽粒", "target": "胚乳", "type": "组成", "evidence": "玉米籽粒由胚、胚乳和种皮组成"},
    {"source": "玉米籽粒", "target": "种皮", "type": "组成", "evidence": "玉米籽粒由胚、胚乳和种皮组成"},
    {"source": "胚乳", "target": "淀粉", "type": "主要成分为", "evidence": "胚乳以淀粉为主"}
  ],
  "candidates": {"entities": [], "relations": []},
  "warnings": []
}

---示例（中等长度）---
输入正文：
稻（Oryza sativa L.）为禾本科稻属一年生草本作物，通称水稻。稻秆直立，叶片长披针形。

输出JSON：
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_static"},
  "entities": [
    {"name": "稻", "type": "作物", "description": null, "aliases": ["Oryza sativa L."], "attributes": {"生命周期": "一年生", "生长型": "草本", "秆": "直立", "叶形": "长披针形"}},
    {"name": "禾本科", "type": "分类", "description": null, "aliases": [], "attributes": {}},
    {"name": "稻属", "type": "分类", "description": null, "aliases": [], "attributes": {}},
    {"name": "水稻", "type": "作物", "description": null, "aliases": [], "attributes": {}}
  ],
  "relations": [
    {"source": "稻", "target": "禾本科", "type": "属于", "evidence": "稻（Oryza sativa L.）为禾本科稻属一年生草本作物"},
    {"source": "稻", "target": "稻属", "type": "属于", "evidence": "稻（Oryza sativa L.）为禾本科稻属一年生草本作物"},
    {"source": "稻", "target": "水稻", "type": "别名", "evidence": "为禾本科稻属一年生草本作物，通称水稻"}
  ],
  "candidates": {"entities": [], "relations": []},
  "warnings": []
}

---示例（短文本）---
输入正文：
水稻属于禾本科作物，玉米属于禾本科作物。

输出JSON：
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_static"},
  "entities": [
    {"name": "水稻", "type": "作物", "description": null, "aliases": [], "attributes": {}},
    {"name": "玉米", "type": "作物", "description": null, "aliases": [], "attributes": {}},
    {"name": "禾本科作物", "type": "分类", "description": null, "aliases": [], "attributes": {}}
  ],
  "relations": [
    {"source": "水稻", "target": "禾本科作物", "type": "属于", "evidence": "水稻属于禾本科作物"},
    {"source": "玉米", "target": "禾本科作物", "type": "属于", "evidence": "玉米属于禾本科作物"}
  ],
  "candidates": {"entities": [], "relations": []},
  "warnings": []
}

---示例（候选）---
输入正文：
施肥处理A可能提高了小麦产量，但未说明试验条件与对照设置。

输出JSON：
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_static"},
  "entities": [
    {"name": "施肥处理A", "type": "管理措施", "description": null, "aliases": [], "attributes": {}},
    {"name": "小麦产量", "type": "属性", "description": null, "aliases": [], "attributes": {}},
    {"name": "对照", "type": "其他", "description": null, "aliases": [], "attributes": {}}
  ],
  "relations": [],
  "candidates": {
    "entities": [],
    "relations": [
      {"source": "施肥处理A", "target": "小麦产量", "type": "提升", "reason": "实验性结论但条件不清晰（处理/对照/时期/地点缺失）", "evidence": "施肥处理A可能提高了小麦产量"}
    ]
  },
  "warnings": []
}

---示例（实验性关系 → candidates）---
输入正文：
施肥处理A显著提高了小麦产量，较常规施肥处理B（对照）提高15%。该结果来自2021年田间试验（山东，春季）。

输出JSON：
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_static"},
  "entities": [
    {"name": "施肥处理A", "type": "管理措施", "description": null, "aliases": [], "attributes": {}},
    {"name": "小麦产量", "type": "属性", "description": null, "aliases": [], "attributes": {}},
    {"name": "常规施肥处理B", "type": "管理措施", "description": null, "aliases": ["对照"], "attributes": {}}
  ],
  "relations": [],
  "candidates": {
    "entities": [],
    "relations": [
      {
        "source": "施肥处理A",
        "target": "小麦产量",
        "type": "提高",
        "reason": "因果/机理/实验结论，应由因果层处理",
        "evidence": "施肥处理A显著提高了小麦产量，较常规施肥处理B（对照）提高15%",
        "attributes": {"conditions": "2021年田间试验（山东，春季），对照=常规施肥处理B"}
      }
    ]
  },
  "warnings": []
}

---示例（阈值/范围 → candidates）---
输入正文：
SO2含量在0.2% - 0.3%之间时，蛋白质网分散适宜；温度过高（>55℃）会抑制乳酸菌发酵。

输出JSON：
{
  "schema_version": "1.0",
  "doc_id": "示例论文",
  "source": {"source_type": "domain_static"},
  "entities": [
    {"name": "SO2含量", "type": "属性", "description": null, "aliases": [], "attributes": {}},
    {"name": "蛋白质网分散", "type": "属性", "description": null, "aliases": [], "attributes": {}},
    {"name": "温度", "type": "属性", "description": null, "aliases": [], "attributes": {}},
    {"name": "乳酸菌发酵", "type": "过程", "description": null, "aliases": [], "attributes": {}}
  ],
  "relations": [],
  "candidates": {
    "entities": [],
    "relations": [
      {
        "source": "SO2含量",
        "target": "蛋白质网分散",
        "type": "影响",
        "reason": "因果/机理/实验结论，应由因果层处理",
        "evidence": "SO2含量在0.2% - 0.3%之间时，蛋白质网分散适宜"
      },
      {
        "source": "温度",
        "target": "乳酸菌发酵",
        "type": "抑制",
        "reason": "因果/机理/实验结论，应由因果层处理",
        "evidence": "温度过高（>55℃）会抑制乳酸菌发酵"
      }
    ]
  },
  "warnings": []
}
"""

SYSTM_PROMPT = """---角色---
你是农业领域知识抽取专家，负责从论文正文中抽取实体与关系，
用于构建可追溯的农业知识图谱。

---硬约束---
1) **事实约束**：只抽取正文明确陈述的“稳定事实/定义/分类/组成/属性/用途/适用范围/管理措施/方法”；
   明确排除因果/机理/效果性结论（如影响/提高/降低/促进/抑制/相关/导致等）；禁止凭表格数值推断。
2) **引用约束**：relation 中的 source/target 必须出现在 entities。
3) **条件处理**：出现时间/阶段/试验结果/显著性比较/相关性/提升降低（如正相关/显著提高/先增后减）等，
   视为因果/机理/实验结论，不进入静态 relations：
   - 定义性时间事实（如生育期/成熟期/抽穗期等明确定义）允许进入 relations 或 entities.attributes。
   - 实验性/条件性/对比性结果放入 candidates.relations，并在 reason 标注“因果/机理/实验结论，应由因果层处理”，
     同时写明 conditions（处理/对照/时期/地点等）。
   - 出现范围/阈值/最适/过高/过低/抑制/促进/显著/提高/降低等效应触发词时，只进入 candidates。
4) **关系类型**：允许动态发现，但必须简短，禁止带数字或单位；type 优先使用动词或动宾短语，不包含副词/程度词/频率词。
5) **证据**：evidence 必须为原文同句的连续片段（不少于6字）；若句子很短，取同句中最小完整短语扩展到 >=6 字。
6) **指代消解**：不得将“本文/本研究/本试验/本实验/该处理/上述/其/它/本品种”等作为实体。
   - 若能在前一句找到明确对象，需替换为该对象名称。
   - 若存在多个候选或无法消解，放入 candidates。
7) **论文指代**：若出现“本文/本研究/本试验”等指代当前论文，且上下文提供 doc_id，
   必须将 doc_id 作为实体（类型=文献）参与关系。
8) **输出**：只输出单个 JSON 对象，不要输出多余文本或 Markdown。
9) **类型收敛**：优先使用建议类型；若原文明确给出且不在列表内，可创建新类型。
   - 新类型必须为原文中的名词短语，简短清晰，不含数字/单位/长修饰。
   - 类型不确定时进入 candidates。
10) **属性约束**：attributes 的值必须是简短标量（数字/布尔/短语）；若包含独立概念或长句，改为关系或 candidates。
11) **嵌套实体**：遇到复合名词（如“冬小麦品种济麦22”），应拆成实体并建立“属于/是”的关系；
    除非该名词为不可分割的专有名词。

---未知探索（必须执行）---
1) 若出现定义性触发词（如“属于/被称为/是指/简称/又称/划分为/由…组成/主要成分”），
   但类型/关系不确定时才进入 candidates；纯描述性/修辞性/背景性语句不要进入任何列表。
2) 若出现明确知识陈述（定义/分类/组成/属性/用途/适用范围/管理措施），但无法判断其稳定性或类型，也应进入 candidates。
3) candidates 必须包含 reason 与 evidence，便于人工校验；reason 需具体清晰。
   - 示例：定义性触发词存在，但是否为稳定分类需人工判断。
   - 示例：涉及时间条件，可能属于时序或实验事实。
   - 示例：关系语义不够明确，需人工确认边界。
4) **农业覆盖优先**：遇到农业名词短语（作物/品种/病虫害/性状/指标/栽培措施/设备/地理区域/试验处理/对照/肥料/农药/气象因子/土壤类型/加工产品），优先抽取为实体；类型不确定可入 candidates。

---输出前自检（不要输出自检内容）---
1) 指代还原：将“该品种/其/本研究”等替换为具体实体。
2) 事实判别：静态事实入 entities/relations；实验或比较语句进入 candidates（因果/机理归因），
   条件不清晰时明确写入 reason。
3) 属性归一：attributes 值必须是简短标量，长句拆为关系或 candidates。
4) 完整性：relations 的 source/target 必须在 entities 中存在。
"""

TSK_PROMPT = r"""---任务---
从输入正文中抽取实体与关系，并以统一 JSON 结构输出。

---输出 JSON 结构---
{
  "schema_version": "1.0",
  "doc_id": "{doc_id}",
  "source": {"source_type": "domain_static"},
  "entities": [
    {"name": "...", "type": "...", "description": null, "aliases": [], "attributes": {}}
  ],
  "relations": [
    {"source": "...", "target": "...", "type": "...", "evidence": "...", "attributes": {}}
  ],
  "candidates": {
    "entities": [
      {"name": "...", "type": "...", "reason": "...", "evidence": "..."}
    ],
    "relations": [
      {"source": "...", "target": "...", "type": "...", "reason": "...", "evidence": "..."}
    ]
  },
  "warnings": []
}

---实体类型建议（允许扩展）---
生物体/作物/品种/病害/虫害/杂草/病原、非生物要素/土壤/气象/养分/生态区/地理区域/试验地点、
农化品/肥料/农药/调节剂、农机/装备/部件/设施、技术/方法/管理措施/栽培方式/栽培制度/播种方式、
试验处理/对照/试验设计、性状/指标/参数/品质指标/产量构成/工艺参数、遗传要素/基因/位点/QTL/分子标记、
材料/物质/激素/酶/代谢物/商品名/机制/文献/部位/其他

---关系类型建议（允许扩展）---
属于、上位分类、下位分类、别名、组成、原料为、有效成分、商品名为、
适用于、具有、危害、宿主于、用途、来源于、可分解为、划分为

---注意事项---
- 中英文并列时，实体名称优先中文，英文写入 aliases。
- 括号内英文、缩写、商品英文名默认写入 aliases，除非文本明确将其作为独立命名对象。
- 若为实验性/条件性/对比性结论，放入 candidates.relations，并在 reason 写明“因果/机理/实验结论”，同时补充 conditions。
- 输出时结构字段不可省略；标量缺失使用 null，列表缺失使用 []。
- description 仅在原文有定义性表述时填写；否则保持 null，不得用别名或属性替代。
- attributes 的键允许中文，保持简短名词，可对原文名词短语做必要归一化，不得臆造概念。
- attributes 值必须为简短标量（数字/布尔/短语），不得为长句或复合逻辑。
- 可在 relations.attributes 中补充静态属性（如范围、等级、分类依据）。
- 允许“自主发现”的静态要点，但必须写入 candidates 并给出证据。
- 输出时确保 JSON 完整闭合且语法有效。

{examples}

---输入正文---
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
