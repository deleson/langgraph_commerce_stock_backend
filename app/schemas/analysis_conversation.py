"""分析会话与 ReAct Trace Schema。

本文件定义普通追问、ReAct 追问、工具 Observation 和推理轨迹的持久化结构。
这些结构用于审计 AI 如何回答、是否调用工具以及工具返回了什么。
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.stock_analysis_react import ReactActionType, ReactToolName


ConversationRole = Literal["user", "assistant", "tool", "system"]
ConversationMessageType = Literal[
    "normal_follow_up",
    "react_follow_up",
    "tool_observation",
    "system_summary",
    "error",
]
ConversationSource = Literal[
    "normal_follow_up",
    "react_follow_up",
    "system",
]


class AnalysisConversationMessageCreate(BaseModel):
    """创建一条分析会话消息的数据结构。"""

    user_id: int
    analysis_record_id: int | None = None
    analysis_thread_id: str = Field(min_length=1, max_length=120)
    role: ConversationRole
    message_type: ConversationMessageType
    content: str | None = None
    payload: dict[str, Any] | None = None
    source: ConversationSource
    sequence_no: int = Field(ge=1)

    @field_validator("analysis_thread_id", mode="before")
    @classmethod
    def normalize_analysis_thread_id(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class AnalysisConversationMessageResponse(BaseModel):
    """分析会话消息响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    analysis_record_id: int | None
    analysis_thread_id: str
    role: str
    message_type: str
    content: str | None
    payload: dict[str, Any] | None
    source: str
    sequence_no: int
    created_at: datetime


class AnalysisConversationMessageQuery(BaseModel):
    """分析会话消息查询条件。"""

    analysis_thread_id: str = Field(min_length=1, max_length=120)
    role: ConversationRole | None = None
    message_type: ConversationMessageType | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("analysis_thread_id", mode="before")
    @classmethod
    def normalize_analysis_thread_id(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class AnalysisConversationContextMessage(BaseModel):
    """传给追问服务或图节点使用的上下文消息。"""

    role: ConversationRole
    content: str | None = None
    payload: dict[str, Any] | None = None
    message_type: ConversationMessageType
    sequence_no: int


class AnalysisConversationContext(BaseModel):
    """某个分析线程的会话上下文。"""

    analysis_thread_id: str
    messages: list[AnalysisConversationContextMessage] = Field(default_factory=list)
    message_count: int = 0


class AnalysisReactTraceCreate(BaseModel):
    """创建 ReAct 推理轨迹的数据结构。"""

    user_id: int
    analysis_record_id: int | None = None
    analysis_thread_id: str = Field(min_length=1, max_length=120)
    react_graph_checkpoint_id: str | None = Field(default=None, max_length=160)
    step: int = Field(ge=1)
    action: ReactActionType
    tool_name: ReactToolName | None = None
    reason: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: dict[str, Any] | list[Any] | str | None = None
    success: bool = True
    error_message: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @field_validator("analysis_thread_id", "react_graph_checkpoint_id", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class AnalysisReactTraceResponse(BaseModel):
    """ReAct 推理轨迹响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    analysis_record_id: int | None
    analysis_thread_id: str
    react_graph_checkpoint_id: str | None
    step: int
    action: str
    tool_name: str | None
    reason: str | None
    tool_input: dict[str, Any] | None
    tool_output: dict[str, Any] | list[Any] | str | None
    success: bool
    error_message: str | None
    duration_ms: int | None
    created_at: datetime


class AnalysisReactTraceQuery(BaseModel):
    """ReAct 推理轨迹查询条件。"""

    analysis_thread_id: str = Field(min_length=1, max_length=120)
    react_graph_checkpoint_id: str | None = Field(default=None, max_length=160)
    tool_name: ReactToolName | None = None
    success: bool | None = None
    limit: int = Field(default=100, ge=1, le=500)

    @field_validator("analysis_thread_id", "react_graph_checkpoint_id", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value
