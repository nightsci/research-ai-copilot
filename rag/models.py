"""来源信息贯穿整个流程，页码始终是 PDF 的物理页序号（从 1 开始）。"""
from dataclasses import dataclass, field


class RagError(Exception):
    """可向用户直接展示且不泄露请求、密钥或文档内容的错误。"""


@dataclass(frozen=True)
class Page:
    number: int
    text: str


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    pages: tuple[Page, ...]
    empty_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    document_name: str
    page: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Evidence:
    label: str
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class Citation:
    evidence: Evidence
    quote: str


@dataclass(frozen=True)
class Claim:
    text: str
    citations: tuple[Citation, ...]


@dataclass
class Answer:
    question: str
    status: str
    message: str
    evidence: list[Evidence] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    trace: dict = field(default_factory=dict)
