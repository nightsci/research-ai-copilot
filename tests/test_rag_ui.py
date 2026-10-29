from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from rag.llm import ModelConfig
from pdf_helpers import pdf_bytes


class Upload:
    name = "actual-test.pdf"

    def __init__(self):
        self.data = pdf_bytes(["Polysilazane coating improves corrosion resistance in experiments."])
        self.size = len(self.data)

    def getvalue(self):
        return self.data


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_rag_navigation_upload_index_search_and_reset():
    entry = Path(__file__).resolve().parents[1] / "research-ai-copilot.py"
    app = AppTest.from_file(entry, default_timeout=20).run()
    with patch("rag.ui.read_config", return_value=ModelConfig()), patch("rag.llm.requests.post") as model_http:
        app.radio(key="feature_page").set_value("论文阅读").run()
        assert not app.exception
        assert any("AI 生成回答暂未开放" in s.value for s in app.caption)
        upload = Upload()
        with patch("rag.ui.st.file_uploader", return_value=[upload]):
            app.run()
            button(app, "解析论文").click().run()
            assert not app.exception
            assert any("解析完成" in s.value for s in app.success)
            app.text_area[0].set_value("What improves corrosion resistance?")
            assert not any(b.label == "生成 AI 回答" for b in app.button)
            button(app, "查找原文依据").click().run()
            assert not app.exception
            answer = app.session_state["rag_answer"]
            assert answer.status == "evidence_only"
            assert answer.evidence[0].chunk.document_name == upload.name
            model_http.assert_not_called()
        with patch("rag.ui.st.file_uploader", return_value=[]):
            app.run()
            assert "rag_answer" not in app.session_state
            assert "rag_index" not in app.session_state
        app.radio(key="feature_page").set_value("文献检索").run()
        assert any(t.value == "探索学术文献" for t in app.header)
        assert not app.exception
