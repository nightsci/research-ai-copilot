"""使用 Streamlit 官方 AppTest 验证界面状态，测试数据不进入生产应用。"""
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest
from scholar.models import Paper, SearchResult


def test_search_filter_and_validation():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "research-ai-copilot.py", default_timeout=15).run()
    assert not app.exception
    result = SearchResult(papers=[Paper(title="UI test only", year=2024, journal="Surface",
                                        doi="10.1234/test", url="https://doi.org/10.1234/test")],
                          counts={"Crossref": 1}, errors={"OpenAlex": "测试限流提示"})
    with patch("scholar.ui.search_papers", return_value=result):
        app.button[0].click().run()
    assert not app.exception and len(app.warning) == 1
    assert app.metric[2].value == "1"
    app.text_input(key="journal_filter").set_value("not present").run()
    assert app.metric[2].value == "0"
    app.text_input[0].set_value(" ")
    app.button[0].click().run()
    assert not app.exception and len(app.error) == 1
    assert "search_result" not in app.session_state
