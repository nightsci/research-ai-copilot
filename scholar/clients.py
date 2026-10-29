"""真实 API 适配层：超时、有限重试、错误翻译和 JSON 结构检查。"""
from urllib.parse import quote
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from scholar.models import Paper
from scholar.parsers import parse_crossref, parse_openalex


class SourceError(Exception):
    """可直接向用户展示的错误，不包含密钥或原始请求 URL。"""


class AcademicClient:
    def __init__(self, api_key: str = "", email: str = ""):
        self.api_key = api_key
        self.email = email

    def _get(self, url: str, params: dict, *, openalex: bool = False) -> dict:
        retry = Retry(total=2, backoff_factor=0.7, backoff_max=3,
                      status_forcelist=[500, 502, 503, 504],
                      allowed_methods=["GET"], respect_retry_after_header=False)
        headers = {"User-Agent": "ResearchAICopilot/0.1", "Accept": "application/json"}
        if openalex and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.email:
            params = {**params, "mailto": self.email}
        try:
            with requests.Session() as session:
                session.mount("https://", HTTPAdapter(max_retries=retry))
                response = session.get(url, params=params, headers=headers, timeout=(8, 20))
                if response.status_code == 404:
                    return {}
                if response.status_code in (401, 403):
                    raise SourceError("访问被拒绝：请检查 API key、账户状态或网络访问权限。")
                if response.status_code == 429:
                    raise SourceError("请求限流或额度用尽，请稍后重试；OpenAlex 可配置自己的 API key。")
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise SourceError("接口响应格式异常，请稍后重试。")
                return data
        except requests.Timeout as exc:
            raise SourceError("连接超时，请检查网络后重试。") from exc
        except requests.RequestException as exc:
            raise SourceError("网络或上游服务异常，请稍后重试。") from exc
        except ValueError as exc:
            raise SourceError("接口没有返回有效 JSON。") from exc

    def search(self, source: str, query: str, limit: int = 25,
               start: int | None = None, end: int | None = None,
               doi: str = "") -> list[Paper]:
        if source == "OpenAlex":
            url = "https://api.openalex.org/works"
            params = {"per_page": limit}
            if doi:
                url += "/" + quote("https://doi.org/" + doi, safe="/:")
                params = {}
            else:
                params["search"] = query
                filters = []
                if start is not None:
                    filters.append(f"from_publication_date:{start}-01-01")
                if end is not None:
                    filters.append(f"to_publication_date:{end}-12-31")
                if filters:
                    params["filter"] = ",".join(filters)
            data = self._get(url, params, openalex=True)
            if not data:
                return []
            items = [data] if doi else data.get("results")
            parser = parse_openalex
        elif source == "Crossref":
            url = "https://api.crossref.org/works"
            params = {"query.bibliographic": query, "rows": limit}
            if doi:
                url += "/" + quote(doi, safe="")
                params = {}
            else:
                filters = []
                if start is not None:
                    filters.append(f"from-pub-date:{start}-01-01")
                if end is not None:
                    filters.append(f"until-pub-date:{end}-12-31")
                if filters:
                    params["filter"] = ",".join(filters)
            data = self._get(url, params)
            if not data:
                return []
            message = data.get("message")
            if not isinstance(message, dict):
                raise SourceError("Crossref 响应结构异常。")
            items = [message] if doi else message.get("items")
            parser = parse_crossref
        else:
            raise ValueError("未知数据来源")
        if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
            raise SourceError("论文列表格式异常。")
        try:
            return [parser(item) for item in items]
        except (TypeError, AttributeError, IndexError, ValueError) as exc:
            raise SourceError("论文元数据格式异常，无法解析该来源。") from exc
