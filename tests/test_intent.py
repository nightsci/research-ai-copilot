from rag.intent import identify, overview
from rag.models import Document, Page
from rag.documents import split_document
from rag.retrieval import LocalIndex
from rag.service import ask
from rag.llm import ModelConfig
import pytest


@pytest.mark.parametrize('question,kind', [('这篇论文讲什么','summary'),('怎么做实验','methods'),('实验条件是什么','data'),('为什么变慢','reasoning'),('这个呢','ambiguous'),('什么是cEt','fact')])
def test_routes(question, kind):
    assert identify(question).kind == kind


def test_overview_and_clarification_without_model():
    index = LocalIndex(split_document(Document('id','paper.pdf',(Page(1,'Abstract: activation kinetics of phosphoramidites.'),Page(2,'Conclusions: activation rates differ.')))))
    result = ask(index, '这篇论文讲什么', ModelConfig(), use_model=False)
    assert result.status == 'evidence_only' and result.evidence[0].chunk.page == 1
    assert ask(index, '这个呢', ModelConfig()).status == 'clarification'
    assert len(overview(index)) == 2
