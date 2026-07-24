"""
知识抽取模块（MKR v2.0 - 四阶段统一知识抽取）

完全动态Schema的知识抽取系统

核心特性：
1. 四阶段抽取：
   - Stage 1: 静态知识（Entity + Relation + Metadata）
   - Stage 2: 事件知识（Event + Entity-Event 关系）
   - Stage 3: 时序知识（Event-Event 时序关系）
   - Stage 4: 因果机制（Event-Event 因果 + 深度机制建模）

2. 完全动态Schema（零采样）：
   - LLM自主发现entity_type, relation_type, event_type
   - 无需预采样，真正的zero-shot

使用说明：
- 统一使用四阶段管线：`src/core/extraction/four_stage/`
- 运行入口：`scripts/extraction/`
"""

# ============ LLM客户端 ============
from src.core.llm.llm_client import LLMClient, create_llm_client

# ============ 导出 ============
__all__ = [
    # LLM客户端
    'LLMClient',
    'create_llm_client',
]
