from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from scholar.ui import setting


def test_secrets_fallback_and_environment_precedence(monkeypatch):
    monkeypatch.delenv('LLM_MODEL', raising=False)
    with patch('scholar.ui.st.secrets', {'LLM_MODEL':'configured-model'}):
        assert setting('LLM_MODEL') == 'configured-model'
        monkeypatch.setenv('LLM_MODEL','environment-model')
        assert setting('LLM_MODEL') == 'environment-model'


def test_dotenv_is_scoped_to_deployment():
    root=Path(__file__).resolve().parents[1]
    with patch('scholar.ui.load_dotenv') as load:
        app=AppTest.from_file(root/'research-ai-copilot.py', default_timeout=20).run()
    assert not app.exception
    load.assert_called_once_with(root/'.env')
