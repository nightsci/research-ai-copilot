from unittest.mock import Mock, patch
import pytest
from rag.llm import generate
from rag.models import RagError
from rag.ui import read_config


def config(key="test-only-placeholder"):
    values = {"LLM_BASE_URL": "https://api.deepseek.com", "LLM_MODEL": "deepseek-flash",
              "LLM_API_KEY": key, "OPENAI_API_KEY": "must-not-use-this"}
    return read_config(lambda name: values.get(name, ""))


def test_deepseek_payload():
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": '{"insufficient_evidence":true,"claims":[]}'}}]}
    with patch("requests.post", return_value=response) as post:
        generate("test", [], config())
    assert post.call_args.args[0] == "https://api.deepseek.com/chat/completions"
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "deepseek-flash"
    assert payload["max_tokens"] == 2000 and "max_completion_tokens" not in payload
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}


def test_deepseek_missing_key_does_not_use_openai_key():
    with patch("requests.post") as post:
        with pytest.raises(RagError, match="密钥"):
            generate("test", [], config(""))
    post.assert_not_called()


def test_deepseek_insufficient_balance():
    with patch("requests.post", return_value=Mock(status_code=402)):
        with pytest.raises(RagError, match="余额不足"):
            generate("test", [], config())
