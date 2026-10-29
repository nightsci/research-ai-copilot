"""不同来源共用的数据结构。"""
from dataclasses import dataclass, field
import re
from urllib.parse import unquote, urlparse


def normalize_doi(value: str | None) -> str:
    value = unquote(value or "").strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    return value.lower().strip()


def valid_doi(value: str) -> bool:
    return bool(re.fullmatch(r"10\.\d{4,9}/\S+", normalize_doi(value)))


def safe_url(value: str | None) -> str:
    value = value or ""
    parsed = urlparse(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else ""


@dataclass
class Paper:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    journal: str = ""
    doi: str = ""
    url: str = ""
    sources: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    papers: list[Paper] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
