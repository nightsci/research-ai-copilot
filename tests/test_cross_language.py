from unittest.mock import patch
from rag.models import Document, Page
from rag.documents import split_document
from rag.retrieval import LocalIndex
from rag.service import ask
from rag.llm import ModelConfig


def test_cross_language_preserves_evidence_and_threshold():
    text = "Multi-head attention allows attending to different representation subspaces."
    index = LocalIndex(split_document(Document("id", "paper.pdf", (Page(1, text),))))
    assert index.diagnostics("多头注意力有什么作用？")["query_nonzero"] == 0
    assert index.search("多头注意力有什么作用？") == []
    assert index.search(text)[0].score > .99
    with patch("rag.service.translate_query", return_value="What does multi-head attention allow?") as translate, patch("rag.service.generate", return_value='{"insufficient_evidence":true,"claims":[]}') as generate:
        answer = ask(index, "多头注意力有什么作用？", ModelConfig(api_key="test", model="test"))
    translate.assert_called_once()
    generate.assert_called_once()
    assert answer.evidence[0].chunk.text == text
    assert answer.status == "insufficient"
    assert index.diagnostics("test")["threshold"] == .08


def test_no_evidence_after_translation_does_not_generate():
    index = LocalIndex(split_document(Document("id", "paper.pdf", (Page(1, "Attention learns sequence representations."),))))
    with patch("rag.service.translate_query", return_value="volcano magma") , patch("rag.service.generate") as generate:
        result = ask(index, "火山岩浆？", ModelConfig(api_key="test", model="test"))
    assert result.status == "no_evidence"
    generate.assert_not_called()
