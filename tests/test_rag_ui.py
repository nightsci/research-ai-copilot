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
    with patch("rag.ui.read_config", return_value=ModelConfig()):
        app.radio(key="feature_page").set_value("科研 AI 智能问答").run()
        assert not app.exception
        upload = Upload()
        with patch("rag.ui.st.file_uploader", return_value=[upload]):
            app.run()
            button(app, "提取文字并建立索引").click().run()
            assert not app.exception
            assert any("已就绪" in s.value for s in app.success)
            app.text_area[0].set_value("What improves corrosion resistance?")
            button(app, "检索并回答").click().run()
            assert not app.exception
            answer = app.session_state["rag_answer"]
            assert answer.status == "evidence_only"
            assert answer.evidence[0].chunk.document_name == upload.name
        with patch("rag.ui.st.file_uploader", return_value=[]):
            app.run()
            assert "rag_answer" not in app.session_state
            assert "rag_index" not in app.session_state
        app.radio(key="feature_page").set_value("多源学术检索").run()
        assert any(t.value == "📚 Scholar Connector" for t in app.title)
        assert not app.exception
