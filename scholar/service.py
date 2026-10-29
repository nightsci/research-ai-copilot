"""业务编排：同时查询两个来源，保留部分成功结果，统一合并。"""
from concurrent.futures import ThreadPoolExecutor
from scholar.clients import AcademicClient, SourceError
from scholar.models import SearchResult, normalize_doi, valid_doi
from scholar.processing import merge_papers


def search_papers(query: str, sources: tuple[str, ...] = ("OpenAlex", "Crossref"),
                  limit: int = 25, start: int | None = None, end: int | None = None,
                  doi_mode: bool = False, api_key: str = "", email: str = "") -> SearchResult:
    query = query.strip()
    if not query:
        raise ValueError("请输入关键词或 DOI。")
    if not sources or any(s not in ("OpenAlex", "Crossref") for s in sources):
        raise ValueError("请至少选择一个有效数据来源。")
    if not 1 <= limit <= 100:
        raise ValueError("每个来源返回数量应在 1–100 之间。")
    if start is not None and end is not None and start > end:
        raise ValueError("起始年份不能晚于结束年份。")
    doi = normalize_doi(query) if doi_mode else ""
    if doi_mode and not valid_doi(doi):
        raise ValueError("DOI 格式应类似 10.1234/example，也支持 doi.org 链接。")
    client = AcademicClient(api_key, email)
    result = SearchResult()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {s: pool.submit(client.search, s, query, limit, start, end, doi) for s in sources}
        # 保持来源顺序，避免网络快慢改变合并优先级。
        for source, future in futures.items():
            try:
                papers = future.result()
                result.counts[source] = len(papers)
                result.papers.extend(papers)
            except SourceError as exc:
                result.errors[source] = str(exc)
    result.papers = merge_papers(result.papers)
    return result
