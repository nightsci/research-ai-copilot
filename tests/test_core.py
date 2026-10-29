"""这里的最小构造记录仅用于单元测试，从不进入应用搜索结果。"""
import csv
import io
from unittest.mock import Mock, patch
import pytest
import requests
from scholar.clients import AcademicClient, SourceError
from scholar.models import Paper, normalize_doi, valid_doi
from scholar.parsers import parse_crossref, parse_openalex
from scholar.processing import export_csv, filter_papers, merge_papers
from scholar.service import search_papers


def test_openalex_parser():
    p = parse_openalex({"title": "A <i>test</i> &amp; B", "publication_year": 2024,
                       "doi": "https://doi.org/10.1234/ABC", "id": "https://openalex.org/W1",
                       "authorships": [{"author": {"display_name": "Li"}}],
                       "primary_location": {"source": {"display_name": "Journal"}}})
    assert (p.title, p.doi, p.year, p.authors, p.journal) == ("A test & B", "10.1234/abc", 2024, ["Li"], "Journal")
    assert p.url == "https://doi.org/10.1234/abc"


def test_crossref_parser_and_date_fallback():
    p = parse_crossref({"title": ["Test"], "DOI": "10.1234/ABC", "published": {"date-parts": [[]]},
                       "issued": {"date-parts": [[2023, 6]]}, "container-title": ["Journal"],
                       "author": [{"given": "A", "family": "Li"}, {"name": "Research group"}]})
    assert p.year == 2023
    assert p.authors == ["A Li", "Research group"]
    assert p.doi == "10.1234/abc"
    assert p.source_urls == ["https://api.crossref.org/works/10.1234%2Fabc"]


@pytest.mark.parametrize("parser", [parse_openalex, parse_crossref])
def test_missing_metadata(parser):
    p = parser({})
    assert p.year is None and p.authors == [] and p.title == ""


def test_doi_normalization():
    assert normalize_doi(" DOI:10.1234/ABC ") == "10.1234/abc"
    assert valid_doi("https://doi.org/10.1234%2Fabc")
    assert not valid_doi("not-a-doi")


def test_merge_doi_enrichment_and_no_mutation():
    first = Paper(title="Test", doi="https://doi.org/10.1234/ABC", sources=["OpenAlex"])
    second = Paper(title="Test revised", doi="10.1234/abc", authors=["Li"], sources=["Crossref"])
    result = merge_papers([first, second])
    assert len(result) == 1 and result[0].authors == ["Li"]
    assert result[0].sources == ["OpenAlex", "Crossref"]
    assert result[0].title == "Test" and first.authors == []


def test_fallback_merge_and_different_dois():
    a = Paper(title="A coating!", year=2024, authors=["Li"])
    b = Paper(title="a COATING", year=2024, authors=["Li"], doi="10.1234/a")
    c = Paper(title="a coating", year=2024, authors=["Li"], doi="10.1234/b")
    assert len(merge_papers([a, b, c])) == 2
    assert len(merge_papers([Paper(), Paper()])) == 2


def test_year_boundaries_and_journal_filter():
    papers = [Paper(year=y, journal="Surface & Coatings") for y in [2020, 2022, 2024, None]]
    assert [p.year for p in filter_papers(papers, 2020, 2022, "SURFACE")] == [2020, 2022]
    assert len(filter_papers(papers)) == 4
    assert filter_papers(papers, journal="unknown") == []


def test_csv_roundtrip_and_formula_protection():
    data = export_csv([Paper(title='=1+1', authors=['李,明'], journal='A\nB')])
    assert data.startswith(b'\xef\xbb\xbf')
    rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
    assert rows[1][0] == "'=1+1" and rows[1][1] == "李,明" and rows[1][3] == "A\nB"


def test_partial_source_failure():
    def response(source, *args):
        if source == "OpenAlex":
            raise SourceError("限流")
        return [Paper(title="Test", sources=[source])]
    with patch.object(AcademicClient, "search", side_effect=response):
        result = search_papers("test")
    assert result.errors == {"OpenAlex": "限流"}
    assert result.counts == {"Crossref": 1} and len(result.papers) == 1


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_http_errors_are_safe(code):
    response = Mock(status_code=code)
    response.raise_for_status.side_effect = requests.HTTPError("secret-in-url")
    with patch("requests.Session.get", return_value=response):
        with pytest.raises(SourceError) as error:
            AcademicClient(api_key="private-key")._get("https://api.openalex.org/works", {})
    assert "secret" not in str(error.value) and "private-key" not in str(error.value)


def test_timeout_and_invalid_json():
    with patch("requests.Session.get", side_effect=requests.Timeout):
        with pytest.raises(SourceError, match="超时"):
            AcademicClient()._get("https://api.crossref.org/works", {})
    response = Mock(status_code=200)
    response.json.side_effect = ValueError()
    with patch("requests.Session.get", return_value=response):
        with pytest.raises(SourceError, match="JSON"):
            AcademicClient()._get("https://api.crossref.org/works", {})


def test_not_found_and_bad_structure():
    with patch.object(AcademicClient, "_get", return_value={}):
        assert AcademicClient().search("Crossref", "", doi="10.1234/absent") == []
    with patch.object(AcademicClient, "_get", return_value={"results": None}):
        with pytest.raises(SourceError):
            AcademicClient().search("OpenAlex", "test")


def test_query_parameters():
    with patch.object(AcademicClient, "_get", return_value={"results": []}) as get:
        AcademicClient().search("OpenAlex", "test", 25, 2020, 2024)
        assert get.call_args.args[1]["filter"] == "from_publication_date:2020-01-01,to_publication_date:2024-12-31"
    with patch.object(AcademicClient, "_get", return_value={"message": {"items": []}}) as get:
        AcademicClient().search("Crossref", "test", 25, 2020, 2024)
        assert get.call_args.args[1]["filter"] == "from-pub-date:2020-01-01,until-pub-date:2024-12-31"


@pytest.mark.parametrize("kwargs", [{"query": " "}, {"query": "test", "sources": ()},
                                    {"query": "test", "start": 2025, "end": 2020},
                                    {"query": "bad", "doi_mode": True}])
def test_validation(kwargs):
    with pytest.raises(ValueError):
        search_papers(**kwargs)
