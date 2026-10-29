"""筛选、保守去重和适用于 Windows Excel 的 CSV 导出。"""
import csv
from copy import deepcopy
import io
import re
import unicodedata
from scholar.models import Paper, normalize_doi


def normalized_text(value: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def merge_papers(papers: list[Paper]) -> list[Paper]:
    """DOI 优先；缺 DOI 时按标题、年份、首作者一致合并。

    不合并不同 DOI；元数据冲突时保留先到来源的非空值。
    """
    merged: list[Paper] = []
    for original in papers:
        paper = deepcopy(original)
        paper.doi = normalize_doi(paper.doi)
        target = next((p for p in merged if paper.doi and p.doi == paper.doi), None)
        if target is None and paper.title and paper.year and paper.authors:
            candidates = [p for p in merged
                          if not (p.doi and paper.doi)
                          and normalized_text(p.title) == normalized_text(paper.title)
                          and p.year == paper.year and p.authors
                          and normalized_text(p.authors[0]) == normalized_text(paper.authors[0])]
            if len(candidates) == 1:
                target = candidates[0]
        if target is None:
            merged.append(paper)
            continue
        for name in ("title", "authors", "year", "journal", "doi", "url"):
            if not getattr(target, name):
                setattr(target, name, getattr(paper, name))
        target.sources = list(dict.fromkeys(target.sources + paper.sources))
        target.source_urls = list(dict.fromkeys(target.source_urls + paper.source_urls))
    return merged


def filter_papers(papers: list[Paper], start: int | None = None,
                  end: int | None = None, journal: str = "") -> list[Paper]:
    journal = normalized_text(journal)
    return [p for p in papers
            if (start is None or (p.year is not None and p.year >= start))
            and (end is None or (p.year is not None and p.year <= end))
            and (not journal or journal in normalized_text(p.journal))]


def export_csv(papers: list[Paper]) -> bytes:
    def cell(value):
        text = str(value) if value is not None else ""
        # 防止外部元数据在 Excel 中被当成公式。
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["标题", "作者", "年份", "期刊", "DOI", "原文链接", "数据来源", "来源记录"])
    for p in papers:
        writer.writerow(map(cell, [p.title, "; ".join(p.authors), p.year, p.journal,
                                   p.doi, p.url, "; ".join(p.sources), "; ".join(p.source_urls)]))
    return buffer.getvalue().encode("utf-8-sig")
