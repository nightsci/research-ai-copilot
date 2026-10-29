from unittest.mock import patch
from rag.documents import split_document
from rag.models import Document, Page
from rag.retrieval import LocalIndex
from rag.llm import ModelConfig
from rag.service import ask


def test_why_question_includes_causal_passage_and_preserves_uncertainty():
    doc = Document('x','test.pdf',(Page(1,'Activation is slower likely as a result of steric hindrance.'),
                                 Page(2,'Activation kinetics experiments measured a slower rate.')))
    index = LocalIndex(split_document(doc))
    with patch('rag.service.generate',return_value='{"insufficient_evidence":true,"claims":[]}') as generate:
        result = ask(index,'Why is activation slower?',ModelConfig(api_key='test',model='test'),top_k=1)
    prompt, evidence, _ = generate.call_args.args
    assert '限定语' in prompt
    assert any('steric' in e.chunk.text for e in evidence)
    assert result.status == 'insufficient'
