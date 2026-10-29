import json
from unittest.mock import Mock, patch
import pytest
import requests
from rag.documents import MAX_BYTES, parse_pdf, split_document
from rag.llm import ModelConfig, generate
from rag.models import Chunk, Document, Evidence, Page, RagError
from rag.retrieval import LocalIndex
from rag.service import ask, validate_answer
from pdf_helpers import pdf_bytes

TEXT = "Polysilazane coating improves corrosion resistance in salt spray experiments."


@pytest.fixture
def document():
    return parse_pdf("paper.pdf", pdf_bytes([TEXT, "", "Battery capacity decreases during repeated charging cycles."]))


@pytest.fixture
def evidence(document):
    return LocalIndex(split_document(document)).search("polysilazane corrosion coating")


def model_json(evidence, **changes):
    data = {"insufficient_evidence": False, "claims": [{"text": "涂层提高了耐蚀性。", "citations": [
        {"evidence_id": evidence[0].label, "quote": TEXT}]}]}
    data.update(changes)
    return json.dumps(data)


def test_parse_real_pdf_bytes_and_physical_pages(document):
    assert document.pages[0].text == TEXT
    assert document.empty_pages == (2,)
    assert document.pages[2].number == 3
    assert document.id == parse_pdf("renamed.pdf", pdf_bytes([TEXT, "", "Battery capacity decreases during repeated charging cycles."])).id


@pytest.mark.parametrize("data, message", [(b"", "为空"), (b"not pdf", "有效 PDF"),
                                           (b"%PDF-broken", "解析失败"),
                                           (pdf_bytes([""]), "扫描版"),
                                           (pdf_bytes([TEXT], "password"), "加密")])
def test_bad_pdf_errors(data, message):
    with pytest.raises(RagError, match=message):
        parse_pdf("test.pdf", data)


def test_pdf_limits():
    with pytest.raises(RagError, match="20 MB"):
        parse_pdf("large.pdf", b"%PDF-" + b"x" * MAX_BYTES)
    with pytest.raises(RagError, match="200 页"):
        parse_pdf("long.pdf", pdf_bytes([""] * 201))


def test_chunk_offsets_overlap_and_page_boundaries():
    d = Document("abc", "paper.pdf", (Page(1, TEXT * 8), Page(2, TEXT * 2)))
    chunks = split_document(d, size=100, overlap=20)
    assert chunks[0].start == 0
    for c in chunks:
        assert c.text == d.pages[c.page - 1].text[c.start:c.end]
        assert len(c.text) <= 100
    first_page = [c for c in chunks if c.page == 1]
    assert first_page[-1].end == len(d.pages[0].text)
    assert first_page[1].start == first_page[0].end - 20
    with pytest.raises(ValueError):
        split_document(d, size=20, overlap=20)


def test_rank_relevant_evidence_and_no_match(document):
    index = LocalIndex(split_document(document))
    found = index.search("What improves corrosion resistance?")
    assert found[0].chunk.page == 1 and found[0].chunk.document_name == "paper.pdf"
    assert index.search("volcanic eruption magma lava") == []
    assert index.search("the and of") == []


def test_chinese_retrieval():
    d = Document("zh", "论文.pdf", (Page(1, "聚硅氮烷涂层提升了耐腐蚀性能，实验采用盐雾试验。"), Page(2, "电池循环寿命随着温度变化。")))
    assert LocalIndex(split_document(d)).search("涂层的耐腐蚀性能如何？")[0].chunk.page == 1


def test_reference_mapping_cannot_change_page(evidence):
    raw = json.loads(model_json(evidence))
    raw["claims"][0]["citations"][0]["page"] = 999
    raw["claims"][0]["citations"][0]["filename"] = "invented.pdf"
    claims = validate_answer(json.dumps(raw), evidence)
    assert claims[0].citations[0].evidence.chunk.page == 1
    assert claims[0].citations[0].evidence.chunk.document_name == "paper.pdf"
    assert claims[0].citations[0].quote == TEXT


@pytest.mark.parametrize("mutation", ["fake_id", "fake_quote", "empty_quote", "no_refs", "wrong_type"])
def test_invalid_citation_rejected(evidence, mutation):
    data = json.loads(model_json(evidence))
    ref = data["claims"][0]["citations"][0]
    if mutation == "fake_id":
        ref["evidence_id"] = "E999"
    elif mutation == "fake_quote":
        ref["quote"] = "This quote was never in the source paper."
    elif mutation == "empty_quote":
        ref["quote"] = ""
    elif mutation == "no_refs":
        data["claims"][0]["citations"] = []
    else:
        ref["quote"] = 42
    with pytest.raises(RagError, match="引用校验"):
        validate_answer(json.dumps(data), evidence)


@pytest.mark.parametrize("raw", ["not JSON", "[]", "null", '{"insufficient_evidence": "false"}', '{"insufficient_evidence":false,"claims":[]}'])
def test_invalid_answer_structure(evidence, raw):
    with pytest.raises(RagError):
        validate_answer(raw, evidence)


def test_missing_key_retains_evidence(document):
    with patch("requests.post") as post:
        answer = ask(LocalIndex(split_document(document)), "corrosion coating", ModelConfig())
    assert answer.status == "error" and "密钥" in answer.message and answer.evidence
    post.assert_not_called()


def test_evidence_only_and_no_evidence_do_not_call_model(document):
    index = LocalIndex(split_document(document))
    with patch("rag.service.generate") as model:
        assert ask(index, "corrosion", ModelConfig(), False).status == "evidence_only"
        assert ask(index, "volcano magma", ModelConfig()).status == "no_evidence"
    model.assert_not_called()


def test_generated_answer_and_model_abstention(document, evidence):
    index = LocalIndex(split_document(document))
    with patch("rag.service.generate", return_value=model_json(evidence)):
        answer = ask(index, "corrosion", ModelConfig())
    assert answer.status == "answered" and answer.claims[0].citations[0].evidence.chunk.page == 1
    with patch("rag.service.generate", return_value='{"insufficient_evidence":true,"claims":[]}'):
        assert ask(index, "corrosion", ModelConfig()).status == "insufficient"
    with patch("rag.service.generate", return_value="invalid"):
        answer = ask(index, "corrosion", ModelConfig())
    assert answer.status == "error" and answer.evidence and not answer.claims


@pytest.mark.parametrize("status, message", [(401, "认证"), (403, "认证"), (429, "额度"), (500, "不可用"), (400, "不兼容"), (302, "不可用")])
def test_model_http_errors(evidence, status, message):
    with patch("requests.post", return_value=Mock(status_code=status)):
        with pytest.raises(RagError, match=message):
            generate("corrosion", evidence, ModelConfig(api_key="secret", model="test"))


def test_timeout_sanitization_and_payload(evidence):
    config = ModelConfig(api_key="private-secret", model="configured-model", base_url="https://example.org/v1")
    with patch("requests.post", side_effect=requests.Timeout("private-secret")):
        with pytest.raises(RagError, match="超时") as error:
            generate("corrosion", evidence, config)
        assert "private-secret" not in str(error.value)
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": model_json(evidence)}}]}
    with patch("requests.post", return_value=response) as post:
        assert generate("corrosion", evidence, config)
    assert post.call_args.args[0] == "https://example.org/v1/chat/completions"
    sent = post.call_args.kwargs
    assert sent["allow_redirects"] is False
    assert sent["json"]["model"] == "configured-model"
    assert "private-secret" not in json.dumps(sent["json"])
    assert "private-secret" not in repr(config)


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{"finish_reason": "length"}]},
                                    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]}])
def test_bad_model_response(evidence, payload):
    response = Mock(status_code=200)
    response.json.return_value = payload
    with patch("requests.post", return_value=response):
        with pytest.raises(RagError):
            generate("corrosion", evidence, ModelConfig(api_key="test", model="test"))


@pytest.mark.parametrize("kwargs", [{"model": ""}, {"base_url": "http://remote.example/v1"},
                                     {"timeout": 0}, {"token_parameter": "bad"}])
def test_model_config_validation(kwargs):
    args = {"api_key": "test", "model": "test", **kwargs}
    with pytest.raises(RagError):
        ModelConfig(**args).validate()
