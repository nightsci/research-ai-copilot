"""纯解析函数：不访问网络，方便单独测试空字段与来源差异。"""
from html import unescape
import re
from urllib.parse import quote
from scholar.models import Paper, normalize_doi, safe_url


def clean_text(value: str | None) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", "", value or "")).split())


def doi_url(doi: str) -> str:
    return f"https://doi.org/{quote(doi, safe='/')}" if doi else ""


def parse_openalex(item: dict) -> Paper:
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    doi = normalize_doi(item.get("doi"))
    authors = [clean_text((a.get("author") or {}).get("display_name"))
               for a in (item.get("authorships") or [])]
    return Paper(
        title=clean_text(item.get("title") or item.get("display_name")),
        authors=[a for a in authors if a], year=item.get("publication_year"),
        journal=clean_text(source.get("display_name")), doi=doi,
        url=safe_url(location.get("landing_page_url")) or doi_url(doi),
        sources=["OpenAlex"],
        source_urls=[u for u in [safe_url(item.get("id"))] if u],
    )


def parse_crossref(item: dict) -> Paper:
    doi = normalize_doi(item.get("DOI"))
    year = None
    for key in ("published", "published-print", "published-online", "issued"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            year = parts[0][0]
            break
    authors = [clean_text(a.get("name") or " ".join(
        str(a[k]) for k in ("given", "family") if a.get(k)))
        for a in (item.get("author") or [])]
    return Paper(
        title=clean_text((item.get("title") or [""])[0]),
        authors=[a for a in authors if a], year=year,
        journal=clean_text((item.get("container-title") or [""])[0]),
        doi=doi, url=safe_url(item.get("URL")) or doi_url(doi),
        sources=["Crossref"],
        source_urls=[f"https://api.crossref.org/works/{quote(doi, safe='')}" ] if doi else [],
    )
