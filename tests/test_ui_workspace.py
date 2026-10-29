"""工作台交互回归；夹具/模型桩仅用于离线测试。"""
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest
from rag.llm import ModelConfig
from rag.models import Answer
from scholar.models import Paper, SearchResult
from test_rag_ui import Upload, button

ENTRY = Path(__file__).resolve().parents[1] / "research-ai-copilot.py"


@pytest.mark.parametrize("result,expected", [
    (SearchResult(errors={"OpenAlex": "来源超时", "Crossref": "来源超时"}), "所有来源均未成功"),
    (SearchResult(counts={"OpenAlex": 0, "Crossref": 0}), "本次没有符合条件"),
])
def test_empty_or_failed_search_is_explicit(result, expected):
    app = AppTest.from_file(ENTRY).run()
    app.text_input[0].set_value("corrosion")
    with patch("scholar.ui.search_papers", return_value=result):
        button(app, "开始检索").click().run()
    assert not app.exception
    assert any(expected in el.value for el in [*app.error, *app.info])
    assert app.metric[0].value == "0"


def test_search_title_is_escaped_and_filters_preserved():
    app = AppTest.from_file(ENTRY).run()
    app.text_input[0].set_value("10.1234/test")
    next(r for r in app.radio if r.label == "检索方式").set_value("DOI 查询")
    app.checkbox[0].check()
    result = SearchResult(papers=[Paper(title='<img src=x onerror="alert(1)">', year=2024)],
                          counts={"Crossref": 1})
    with patch("scholar.ui.search_papers", return_value=result) as search:
        button(app, "开始检索").click().run()
    assert not app.exception
    assert search.call_args.args[3:6] == (2000, app.number_input[1].value, True)
    assert any("&lt;img" in m.value for m in app.markdown)
    assert not any("<img" in m.value for m in app.markdown)


def test_broken_pdf_has_error_and_no_question_form():
    upload = Upload()
    upload.data = b"not a PDF"
    upload.size = len(upload.data)
    with patch("rag.ui.read_config", return_value=ModelConfig()):
        app = AppTest.from_file(ENTRY).run()
        app.radio(key="feature_page").set_value("论文阅读").run()
        with patch("rag.ui.st.file_uploader", return_value=[upload]):
            app.run()
            button(app, "解析论文").click().run()
        assert not app.exception
        assert app.error
        assert not app.text_area
        assert "rag_index" not in app.session_state


def test_configured_model_requires_explicit_generation_action():
    # 假凭据仅用于渲染；ask 被替换，绝不请求线上模型。
    config = ModelConfig(api_key="test-only", model="test-model")
    with patch("rag.ui.read_config", return_value=config):
        app = AppTest.from_file(ENTRY).run()
        app.radio(key="feature_page").set_value("论文阅读").run()
        with patch("rag.ui.st.file_uploader", return_value=[Upload()]):
            app.run()
            button(app, "解析论文").click().run()
            assert any("发送给模型服务" in c.value for c in app.caption)
            app.text_area[0].set_value("What improves corrosion resistance?")
            with patch("rag.ui.ask", return_value=Answer("test", "insufficient", "当前依据不足")) as ask:
                button(app, "生成 AI 回答").click().run()
                assert ask.call_args.args[3] is True
                assert any("当前依据不足" in w.value for w in app.warning)
                button(app, "查找原文依据").click().run()
                assert ask.call_args.args[3] is False
            assert not app.exception


def test_unrelated_question_keeps_no_evidence_explanation():
    with patch("rag.ui.read_config", return_value=ModelConfig()), patch("rag.llm.requests.post") as http:
        app = AppTest.from_file(ENTRY).run()
        app.radio(key="feature_page").set_value("论文阅读").run()
        with patch("rag.ui.st.file_uploader", return_value=[Upload()]):
            app.run()
            button(app, "解析论文").click().run()
            app.text_area[0].set_value("galactic neutron telescope")
            button(app, "查找原文依据").click().run()
            assert not app.exception
            assert app.session_state["rag_answer"].status == "no_evidence"
            assert app.warning
            http.assert_not_called()
