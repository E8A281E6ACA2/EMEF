"""
知识抽取数据模型
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelBase(BaseModel):
    """基础模型，兼容不同版本的pydantic"""

    class Config:
        extra = "allow"

    def model_dump(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(super(), "model_dump"):
            return super().model_dump(*args, **kwargs)
        return self.dict(*args, **kwargs)


class Entity(ModelBase):
    """实体模型"""

    id: Optional[str] = None
    name: str = Field(..., description="实体名称")
    type: str = Field(..., description="实体类型")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="实体属性")
    section_id: str = Field(..., description="所属Section ID")
    section_title: Optional[str] = Field(None, description="所属Section标题")
    paragraph_index: Optional[int] = Field(None, description="段落序号(1-based)")
    source_located: Optional[bool] = Field(None, description="溯源是否成功")
    locate_method: Optional[str] = Field(None, description="定位方法(evidence/name)")
    doc_id: str = Field(..., description="所属文档ID")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    created_at: Optional[datetime] = None
    concepts: List[str] = Field(default_factory=list, description="概念抽象列表")
    concept_levels: Dict[str, int] = Field(default_factory=dict, description="概念抽象层级")


class Relation(ModelBase):
    """关系模型"""

    id: Optional[str] = None
    source_entity: str = Field(..., description="源实体名称")
    target_entity: str = Field(..., description="目标实体名称")
    relation_type: str = Field(..., description="关系类型")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="关系属性")
    section_id: str = Field(..., description="所属Section ID")
    section_title: Optional[str] = Field(None, description="所属Section标题")
    paragraph_index: Optional[int] = Field(None, description="段落序号(1-based)")
    source_located: Optional[bool] = Field(None, description="溯源是否成功")
    locate_method: Optional[str] = Field(None, description="定位方法(evidence/name)")
    doc_id: str = Field(..., description="所属文档ID")
    evidence: Optional[str] = Field(None, description="支持证据")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    created_at: Optional[datetime] = None
    concepts: List[str] = Field(default_factory=list, description="关系抽象概念")
    concept_levels: Dict[str, int] = Field(default_factory=dict, description="关系抽象层级")


class Event(ModelBase):
    """事件模型"""

    id: Optional[str] = None
    description: str = Field(..., description="事件描述")
    type: str = Field(..., description="事件类型")
    participants: List[str] = Field(default_factory=list, description="参与实体列表")
    section_id: str = Field(..., description="所属Section ID")
    doc_id: str = Field(..., description="所属文档ID")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="事件属性")
    created_at: Optional[datetime] = None
    concepts: List[str] = Field(default_factory=list, description="事件抽象概念")
    concept_levels: Dict[str, int] = Field(default_factory=dict, description="概念抽象层级")


class TemporalRelation(ModelBase):
    """时序关系模型"""

    id: Optional[str] = None
    source_event: str = Field(..., description="源事件描述")
    target_event: str = Field(..., description="目标事件描述")
    relation_type: str = Field(..., description="时序关系类型")
    section_id: str = Field(..., description="所属Section ID")
    doc_id: str = Field(..., description="所属文档ID")
    evidence: Optional[str] = Field(None, description="支持证据")
    created_at: Optional[datetime] = None
    concepts: List[str] = Field(default_factory=list, description="时序关系抽象概念")
    concept_levels: Dict[str, int] = Field(default_factory=dict, description="概念抽象层级")


class CausalRelation(ModelBase):
    """因果关系模型"""

    id: Optional[str] = None
    cause_event: str = Field(..., description="原因事件")
    effect_event: str = Field(..., description="结果事件")
    mechanism: List[str] = Field(default_factory=list, description="机制步骤")
    conditions: List[str] = Field(default_factory=list, description="前提条件")
    strength: float = Field(default=0.6, ge=0.0, le=1.0, description="因果强度")
    polarity: str = Field(default="促进", description="因果极性")
    section_id: str = Field(..., description="所属Section ID")
    doc_id: str = Field(..., description="所属文档ID")
    evidence: Optional[str] = Field(None, description="支持证据")
    created_at: Optional[datetime] = None
    polarity_concepts: List[str] = Field(default_factory=list, description="极性概念抽象")
    polarity_concept_levels: Dict[str, int] = Field(default_factory=dict, description="极性概念层级")


class Section(ModelBase):
    """Section节点模型"""

    id: str = Field(..., description="Section ID")
    doc_id: str = Field(..., description="所属文档ID")
    parent_id: Optional[str] = Field(None, description="父Section ID")
    level: int = Field(..., description="层级")
    title: str = Field(..., description="Section标题")
    content: str = Field(..., description="Section内容")
    summary: Optional[str] = Field(None, description="Section摘要")
    token_count: int = Field(..., description="Token数量")
    created_at: Optional[datetime] = None


class Author(ModelBase):
    """作者模型"""

    name: str = Field(..., description="作者姓名")
    role: Optional[str] = Field(None, description="作者角色")
    affiliation: Optional[str] = Field(None, description="所属机构")
    affiliation_id: Optional[str] = Field(None, description="机构编号")
    address: Optional[str] = Field(None, description="通讯地址")
    email: Optional[str] = Field(None, description="邮箱")


class Reference(ModelBase):
    """参考文献模型"""

    id: str = Field(..., description="引用标识")
    raw_text: str = Field(..., description="原始参考文献文本")
    authors: List[str] = Field(default_factory=list, description="作者列表")
    title: Optional[str] = Field(None, description="论文标题")
    journal: Optional[str] = Field(None, description="期刊名")
    year: Optional[int] = Field(None, description="发表年份")
    volume: Optional[str] = Field(None, description="卷号")
    issue: Optional[str] = Field(None, description="期号")
    pages: Optional[str] = Field(None, description="页码范围")
    doi: Optional[str] = Field(None, description="DOI")
    reference_type: str = Field(default="journal", description="文献类型")


class Citation(ModelBase):
    """引用关系模型"""

    reference_id: str = Field(..., description="参考文献ID")
    citation_context: str = Field(..., description="引用上下文")
    citation_purpose: Optional[str] = Field(None, description="引用目的")
    section_id: str = Field(..., description="所属Section ID")
    doc_id: str = Field(..., description="所属文档ID")


class PaperMetadata(ModelBase):
    """论文元数据模型"""

    doc_id: str = Field(..., description="文档ID")
    title: Optional[str] = Field(None, description="论文标题")
    authors: List[Author] = Field(default_factory=list, description="作者列表")
    abstract: Optional[str] = Field(None, description="摘要")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    classification: Dict[str, Any] = Field(default_factory=dict, description="分类信息")
    journal: Optional[str] = Field(None, description="期刊名")
    year: Optional[int] = Field(None, description="发表年份")
    doi: Optional[str] = Field(None, description="DOI")
    references: List[Reference] = Field(default_factory=list, description="参考文献列表")
    citations: List[Citation] = Field(default_factory=list, description="文内引用列表")
    created_at: Optional[datetime] = None


class ExtractionResult(ModelBase):
    """完整抽取结果"""

    section: Section
    metadata: Optional[PaperMetadata] = Field(None, description="论文元数据")
    entities: List[Entity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    temporal_relations: List[TemporalRelation] = Field(default_factory=list)
    causal_relations: List[CausalRelation] = Field(default_factory=list)
    stages_executed: List[str] = Field(default_factory=list, description="执行阶段列表")
    run_id: Optional[str] = Field(None, description="运行ID")
    run_timestamp: Optional[str] = Field(None, description="运行时间戳")
