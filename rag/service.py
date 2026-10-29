"""证据不足时拒答；来源信息由程序填入，绝不接受模型生成的页码。"""
import json
from rag.documents import normalize_space
from rag.llm import ModelConfig, generate
from rag.models import Answer, Citation, Claim, Evidence, RagError
from rag.retrieval import LocalIndex
from rag.query import translate_query
import logging
import re
from rag.intent import identify, overview


def validate_answer(raw: str, evidence: list[Evidence]) -> list[Claim]:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or type(data.get("insufficient_evidence")) is not bool:
            raise ValueError()
        if data["insufficient_evidence"]:
            return []
        entries = data.get("claims")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 6:
            raise ValueError()
        lookup = {e.label: e for e in evidence}
        claims = []
        for entry in entries:
            text = entry["text"]
            refs = entry["citations"]
            if not isinstance(text, str) or not text.strip() or len(text) > 1800:
                raise ValueError()
            if not isinstance(refs, list) or not 1 <= len(refs) <= 5:
                raise ValueError()
            citations = []
            for ref in refs:
                item = lookup[ref["evidence_id"]]
                if not isinstance(ref["quote"], str):
                    raise ValueError()
                quote = normalize_space(ref["quote"])
                if len(quote) < 12 or quote not in normalize_space(item.chunk.text):
                    raise ValueError()
                citations.append(Citation(item, quote))
            claims.append(Claim(text.strip(), tuple(citations)))
        return claims
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise RagError("模型回答未通过引用校验（编号、原文摘录或结构无效），已拒绝展示。请查看真实证据或重新提问。") from exc


def _ask(index: LocalIndex, question: str, config: ModelConfig,
        use_model: bool = True, top_k: int = 5, trace: dict | None = None) -> Answer:
    question = question.strip()
    if not question or len(question) > 2000:
        raise RagError("请输入 1–2000 字符的问题。")
    evidence = index.search(question, top_k=top_k)
    intent = identify(question)
    if intent.clarification:
        return Answer(question, "clarification", intent.clarification)
    retrieval_query = question
    logging.getLogger(__name__).info("retrieval diagnostics: %s", index.diagnostics(question))
    if use_model and config.api_key and index.needs_english_query(question):
        try:
            translated = translate_query(question, config)
            retrieval_query = translated
            if trace is not None:
                trace['retrieval_query'] = translated
            translated_evidence = index.search(translated, top_k=top_k)
            logging.getLogger(__name__).info("translated retrieval diagnostics: %s", index.diagnostics(translated))
            # 只使用原 PDF 检索出的证据，翻译文本从不作为引用。
            if translated_evidence:
                evidence = translated_evidence
        except RagError as exc:
            if not evidence:
                return Answer(question, "error", str(exc))
    if intent.kind == "summary":
        evidence = [Evidence(f"E{i+1}", c, 0.0) for i, c in enumerate(overview(index, top_k))]
    elif intent.kind in ("methods", "data"):
        # 章节词补充局部问题，相关性阈值保持不变。
        extra = index.search(retrieval_query + " " + intent.section_query, top_k=top_k)
        evidence = extra or evidence
    if not evidence:
        # 一次有界的二次检索：去掉问句功能词，保留实义词，阈值仍为 0.08。
        from rag.retrieval import tokens
        retry = " ".join(w for w in tokens(retrieval_query) if w not in {"paper", "study", "research", "does", "investigate"})
        evidence = index.search(retry, top_k=top_k)
    if evidence and intent.kind in ("reasoning", "data", "methods"):
        selected = [e.chunk for e in evidence]
        if intent.kind == "reasoning":
            from rag.retrieval import tokens
            query_terms = set(tokens(retrieval_query))
            # 因果问题补充包含因果或假设措辞、且共享问题实义词的原文片段。
            causal = [c for c in index.chunks
                      if re.search(r"because|as a result|attribut|hypothes|可能由于|原因", c.text, re.I)
                      and query_terms.intersection(tokens(c.text))]
            for c in causal[:2]:
                if c not in selected and len(selected) < 8:
                    selected.append(c)
        for e in evidence[:2]:
            pos = index.chunks.index(e.chunk)
            for j in (pos - 1, pos + 1):
                if 0 <= j < len(index.chunks):
                    c = index.chunks[j]
                    if c.document_id == e.chunk.document_id and c not in selected and len(selected) < 8:
                        selected.append(c)
        evidence = [Evidence(f"E{i+1}", c, next((e.score for e in evidence if e.chunk == c), 0.0)) for i, c in enumerate(selected)]
    if not evidence:
        return Answer(question, "no_evidence", "没有检索到足够相关的原文，无法依据当前论文回答。请使用论文中的术语重新提问。")
    if not use_model:
        return Answer(question, "evidence_only", "已检索原文证据；尚未调用模型生成回答。", evidence)
    try:
        generation_question = question
        if intent.kind == "reasoning":
            generation_question += "\n请区分作者提出的原因/假设与实验观测。likely、可能等限定语必须保留；偶联较慢的推测不能写成已证明的活化分子机制。若没有直接机制证据，请明确说明。"
        raw = generate(generation_question, evidence, config)
        try:
            claims = validate_answer(raw, evidence)
        except RagError:
            if trace is not None:
                trace['citation_retry'] = True
            claims = validate_answer(generate(generation_question + "\n引用校验要求：只逐字复制片段中的连续原文，保留符号；不要改写引文。", evidence, config), evidence)
    except RagError as exc:
        return Answer(question, "error", str(exc), evidence)
    if not claims:
        return Answer(question, "insufficient", "已检索到相关片段，但其内容不足以支持该问题的答案。", evidence)
    return Answer(question, "answered", "回答中的引用编号与原文摘录已核验。请结合原文判断结论是否成立。", evidence, claims,
                  {"retrieval_query": retrieval_query})


def ask(index: LocalIndex, question: str, config: ModelConfig,
        use_model: bool = True, top_k: int = 5) -> Answer:
    trace = {"retrieval_query": question}
    answer = _ask(index, question, config, use_model, top_k, trace)
    answer.trace.update(trace)
    answer.trace.update({"original_question": question, "intent": identify(question).kind,
                    "threshold": 0.08, "baseline": index.diagnostics(question)})
    if answer.status in ("no_evidence", "insufficient"):
        context = [Evidence(f"T{i+1}", c, 0.0) for i, c in enumerate(overview(index))]
        answer.message += " 已补充标题、摘要或结论候选供核查。当前检索未发现目标内容，不能仅凭检索结果断言全文不存在。"
        if context:
            answer.message += " 论文主题线索（首页提取原文）：" + context[0].chunk.text[:350]
        answer.evidence.extend(context)
        if use_model and config.api_key and any(w in question for w in ("有没有研究", "是否涉及", "是否研究")):
            from rag.scope import check_scope
            try:
                claims = check_scope(question, index, context, config)
                if claims:
                    answer.status = "out_of_scope"
                    answer.claims = claims
                    answer.message = "已核查可提取全文、标题/摘要/结论候选及相关检索结果：在这份论文的已解析文本中，未发现你询问的材料与性能研究。下列引用说明论文实际研究主题。此结论不覆盖无法提取的图片或缺失页面。"
            except RagError as exc:
                answer.trace['scope_error'] = str(exc)
    return answer
