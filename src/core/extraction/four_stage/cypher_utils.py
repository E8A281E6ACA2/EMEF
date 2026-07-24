"""
Cypher 生成工具函数
用于 Neo4j 知识图谱导出
"""

from __future__ import annotations

import os
import re
from typing import List

# 高频实体类型列表（会作为 Neo4j 的额外标签）
HIGH_FREQ_ENTITY_TYPES = {
    "作物",
    "肥料",
    "产量指标",
    "性状",
    "基因",
    "蛋白质",
    "组织",
    "方法",
    "地点",
    "时间",
    "机构",
    "化合物",
    "土壤",
    "实验设计",
    "测量指标",
    "变量",
    "参数",
    "设备",
    "材料",
    "试剂",
    "作物品种",
    "研究机构",
    "生理指标",
    "土壤指标",
    "施肥处理",
    "表型",
    "染色体",
    "期刊",
    "论文",
    "作者",
    "关键词",
    "生态指标",
    "土壤问题",
    "效率指标",
}

GENERIC_ENTITY_TYPES = {
    "实体",
    "概念",
    "对象",
    "变量",
    "指标",
    "entity",
    "thing",
}


def sanitize_label(label: str) -> str:
    """清洗标签名称，去除 Neo4j 不支持的特殊字符"""
    label = label.strip()
    label = (
        label.replace("、", "_")
        .replace("，", "_")
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
        .replace("(", "_")
        .replace(")", "_")
        .replace("（", "_")
        .replace("）", "_")
        .replace("：", "_")
        .replace(":", "_")
    )
    cleaned: List[str] = []
    for ch in label:
        if ch == "_" or ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    label = "".join(cleaned)
    label = re.sub(r"_+", "_", label).strip("_")
    if not label:
        return "entity"
    if label[0].isdigit():
        label = f"L_{label}"
    return label


def _env_bool(names: List[str], default: bool) -> bool:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def should_apply_type_label(entity_type: str) -> bool:
    if not entity_type:
        return False
    if entity_type in GENERIC_ENTITY_TYPES:
        return False
    expand = _env_bool(["EXPAND_ENTITY_LABELS"], True)
    if not expand:
        return entity_type in HIGH_FREQ_ENTITY_TYPES
    if entity_type in HIGH_FREQ_ENTITY_TYPES:
        return True
    if len(entity_type) > 32:
        return False
    return True


def format_entity_label(entity_type: str) -> str:
    if should_apply_type_label(entity_type):
        return f":Entity:{sanitize_label(entity_type)}"
    return ":Entity"


def escape_cypher_string(value: str) -> str:
    """转义 Cypher 字符串值"""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )


def split_cypher_statements(script: str) -> List[str]:
    if not script:
        return []
    statements: List[str] = []
    buf: List[str] = []
    in_single = False
    in_double = False
    escape_next = False
    for ch in script:
        if escape_next:
            buf.append(ch)
            escape_next = False
            continue
        if ch == "\\" and (in_single or in_double):
            buf.append(ch)
            escape_next = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            continue
        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def normalize_relation_type(rel_type: str) -> str:
    """统一关系类型格式"""
    rel_type = (rel_type or "").strip()
    rel_type = rel_type.translate(
        str.maketrans(
            {
                "⁰": "0",
                "¹": "",
                "²": "2",
                "³": "3",
                "⁴": "",
                "⁵": "5",
                "⁶": "6",
                "⁷": "7",
                "⁸": "",
                "⁹": "",
                "㎡": "m2",
                "㎥": "m3",
            }
        )
    )
    rel_type = re.sub(r"\^(\d+)", r"\1", rel_type)
    rel_type = rel_type.replace(" ", "_")
    cleaned: List[str] = []
    for ch in rel_type:
        if ch == "_" or ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    rel_type = "".join(cleaned)
    rel_type = re.sub(r"_+", "_", rel_type).strip("_")
    if not rel_type:
        rel_type = "RELATES_TO"
    if rel_type[0].isdigit():
        rel_type = f"R_{rel_type}"
    has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in rel_type)
    return rel_type if has_chinese else rel_type.upper()
