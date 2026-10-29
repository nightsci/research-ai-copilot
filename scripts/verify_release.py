"""部署副本真实接口验收。显式指定外部 PDF；不保存论文正文或密钥。"""
import argparse
import hashlib
import json
import logging
import os
import re
from pathlib import Path
import time
import tomllib
from dotenv import load_dotenv
from rag.documents import parse_pdf, split_document
from rag.retrieval import LocalIndex
from rag.service import ask
from rag.ui import read_config
from scholar.service import search_papers


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pdf', required=True, type=Path)
    p.add_argument('--question', required=True)
    p.add_argument('--unrelated', required=True)
    args=p.parse_args()
    if not re.search(r'[\u4e00-\u9fff]', args.question) or not re.search(r'[\u4e00-\u9fff]', args.unrelated):
        raise SystemExit('Chinese verification requires intact Chinese questions; check terminal encoding.')
    root=Path(__file__).resolve().parents[1]
    load_dotenv(root/'.env')
    sp=root/'.streamlit/secrets.toml'
    secrets=tomllib.loads(sp.read_text(encoding='utf-8')) if sp.exists() else {}
    config=read_config(lambda k: os.getenv(k) or str(secrets.get(k,'')))
    config.validate()
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    data=args.pdf.read_bytes()
    doc=parse_pdf('verification-paper.pdf',data)
    index=LocalIndex(split_document(doc))
    report={'python_compatible':'3.12','pdf_sha256':hashlib.sha256(data).hexdigest(),
            'pages':len(doc.pages),'chunks':len(index.chunks),'model':config.model,'results':[]}
    for label,q in [('chinese_answer',args.question),('unrelated_refusal',args.unrelated)]:
        start=time.perf_counter();answer=ask(index,q,config)
        citations=[r for c in answer.claims for r in c.citations]
        report['results'].append({'case':label,'status':answer.status,'seconds':round(time.perf_counter()-start,2),
             'citation_pages':[r.evidence.chunk.page for r in citations],
             'verified_quotes':all(r.quote in r.evidence.chunk.text for r in citations),
             'citation_count':len(citations)})
    live=search_papers('polysilazane corrosion coating',limit=10)
    report['scholar']={'counts':live.counts,'errors':live.errors,'merged':len(live.papers)}
    out=root/'artifacts';out.mkdir(exist_ok=True)
    (out/'release-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))
    a,b=report['results']
    assert a['status']=='answered' and a['citation_count'] and a['verified_quotes']
    assert b['status'] in ('out_of_scope','insufficient','no_evidence')
    assert live.papers and not live.errors


if __name__=='__main__':
    main()
