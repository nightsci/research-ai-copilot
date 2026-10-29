import json
from unittest.mock import patch
from rag.scope import check_scope
from rag.models import Document, Page, Evidence
from rag.documents import split_document
from rag.retrieval import LocalIndex
from rag.llm import ModelConfig


def test_scope_requires_actual_topic_quote_and_absent_term():
    text = 'Abstract: We investigate activation kinetics of phosphoramidites.'
    chunks = split_document(Document('x','paper.pdf',(Page(1,text),)))
    index = LocalIndex(chunks)
    context = [Evidence('T1',chunks[0],0)]
    data = {'absent':True,'target_terms':['polysilazane'],'insufficient_evidence':False,
            'claims':[{'text':'本文研究活化动力学。','citations':[{'evidence_id':'T1','quote':text}]}]}
    with patch('rag.scope.request_completion',return_value=json.dumps(data)):
        assert check_scope('是否研究聚硅氮烷',index,context,ModelConfig())
    data['target_terms']=['phosphoramidites']
    with patch('rag.scope.request_completion',return_value=json.dumps(data)):
        assert check_scope('是否研究亚磷酰胺',index,context,ModelConfig()) is None
