from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content_md: Optional[str] = None


class DocumentResponse(BaseModel):
    id: int
    title: str
    file_path: Optional[str] = None
    content_md: Optional[str] = None
    file_type: Optional[str] = None
    file_size: int = 0
    parse_status: str = "pending"
    summary: Optional[str] = None
    word_count: int = 0
    source_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    total: int
    items: List[DocumentResponse]


class DocumentPreviewResponse(BaseModel):
    id: int
    title: str
    content_md: Optional[str] = None
    parse_status: str
    file_type: Optional[str] = None
    source_url: Optional[str] = None


class ClipRequest(BaseModel):
    url: Optional[str] = None          # 服务端抓取的网页地址
    html: Optional[str] = None         # 直接提供的网页 HTML（bookmarklet 用）
    title: Optional[str] = None        # 标题（缺省取网页 <title>）
    tags: List[str] = Field(default_factory=list)


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    usage_count: int = 0

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str
    color: str = "#666666"


class SearchResult(BaseModel):
    id: int
    title: str
    snippet: str
    rank: float

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    total: int
    results: List[SearchResult]


class MessageCreate(BaseModel):
    role: str = "user"
    content: str


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    mode: str = "rag"  # rag | direct | doc
    document_id: Optional[int] = None


class ConversationResponse(BaseModel):
    id: int
    title: Optional[str] = None
    document_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    messages: List[dict] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    conversation_id: Optional[int] = None
    document_id: Optional[int] = None
    message: str


class ChatRAGRequest(BaseModel):
    conversation_id: Optional[int] = None
    message: str
    top_k: int = Field(default=5, ge=1, le=20)


class ChatDirectRequest(BaseModel):
    conversation_id: Optional[int] = None
    message: str


class SettingsUpdate(BaseModel):
    ai_base_url: Optional[str] = None
    ai_model: Optional[str] = None
    ai_embedding_model: Optional[str] = None
    ai_api_key: Optional[str] = None  # 传空字符串表示清除
