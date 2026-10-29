"""科研问答页面；文档和索引仅保存在当前 Streamlit 会话中。"""
import hashlib
from urllib.parse import urlparse
import streamlit as st
from rag.documents import parse_pdf, split_document
from rag.llm import ModelConfig
from rag.models import RagError
from rag.retrieval import LocalIndex
from rag.service import ask


def read_config(setting) -> ModelConfig:
    base_url = setting("LLM_BASE_URL") or "https://api.openai.com/v1"
    try:
        timeout = float(setting("LLM_TIMEOUT") or "45")
    except ValueError as exc:
        raise RagError("LLM_TIMEOUT 必须是 1–120 之间的数字。") from exc
    return ModelConfig(
        api_key=setting("LLM_API_KEY") or (setting("OPENAI_API_KEY") if urlparse(base_url).hostname == "api.openai.com" else ""),
        base_url=base_url,
        model=setting("LLM_MODEL"), timeout=timeout,
        json_mode=(setting("LLM_JSON_MODE") or "true").lower() == "true",
        token_parameter=setting("LLM_TOKEN_PARAMETER") or "max_completion_tokens",
    )


def clear_documents():
    for key in ("rag_index", "rag_documents", "rag_answer", "rag_manifest"):
        st.session_state.pop(key, None)


def render_rag(setting):
    st.header("阅读论文，快速定位关键证据")
    st.write("上传英文论文，查找实验方法、研究结果和原文出处。")
    config = None
    config_error = ""
    try:
        config = read_config(setting)
        config.validate()
    except RagError as exc:
        config_error = str(exc)
    evidence_only = config is not None and not config.api_key
    if evidence_only:
        st.caption("在线版当前支持论文解析和原文证据检索，AI 生成回答暂未开放。")
    elif config_error:
        st.warning("模型暂不可用，仍可上传 PDF 和检索原文证据。")
    with st.sidebar:
        st.subheader("阅读设置")
        with st.expander("更多设置"):
            top_k = st.slider("最多展示证据片段", 1, 8, 5, key="rag_top_k")

    st.subheader("1 · 上传论文")
    st.caption("文字版 PDF · 单文件最多 20 MB / 200 页 · 最多 3 篇，共 30 MB。文档仅在当前会话处理，请勿上传涉密资料。")
    files = st.file_uploader("选择 PDF 论文", type=["pdf"], accept_multiple_files=True, key="rag_uploads")
    for file in files or []:
        size = f"{file.size / 1024:.1f} KB" if file.size < 1024 * 1024 else f"{file.size / 1024 / 1024:.2f} MB"
        st.text(f"{file.name} · {size}")
    manifest = tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in (files or []))
    if st.session_state.get("rag_manifest") != manifest:
        clear_documents()
        st.session_state.rag_manifest = manifest
    if st.button("解析论文", type="primary", disabled=not files):
        st.session_state.pop("rag_answer", None)
        st.session_state.pop("rag_index", None)
        st.session_state.pop("rag_documents", None)
        if len(files) > 3 or sum(f.size for f in files) > 30 * 1024 * 1024:
            st.error("一次最多上传 3 个 PDF，总大小不能超过 30 MB。")
        else:
            docs, seen = [], set()
            with st.spinner("正在按页提取文字并建立本地索引…"):
                for f in files:
                    try:
                        doc = parse_pdf(f.name, f.getvalue())
                        if doc.id in seen:
                            st.info(f"{doc.name} 与已处理文件内容相同，已去重。")
                            continue
                        seen.add(doc.id)
                        docs.append(doc)
                    except RagError as exc:
                        st.error(f"{f.name}：{exc}")
                if docs:
                    try:
                        if sum(len(p.text) for d in docs for p in d.pages) > 1_500_000:
                            raise RagError("本次文档总文字量过大，请减少文件数量。")
                        st.session_state.rag_index = LocalIndex([c for d in docs for c in split_document(d)])
                        st.session_state.rag_documents = docs
                    except RagError as exc:
                        st.error(str(exc))

    docs = st.session_state.get("rag_documents", [])
    if not docs:
        st.caption("上传后点击「解析论文」，即可开始查找原文。")
        return
    index = st.session_state.rag_index
    st.success(f"解析完成：{len(docs)} 篇论文，共 {sum(len(d.pages) for d in docs)} 页。")
    for doc in docs:
        with st.expander("预览论文文字"):
            st.text(doc.name)
            if doc.empty_pages:
                st.warning("这些页面未提取到足够文字（可能是扫描页、空白页或图片页），未进入检索：" + ", ".join(map(str, doc.empty_pages)))
            page = st.selectbox("预览物理页", [p.number for p in doc.pages], key=f"preview_{doc.id}")
            st.text(doc.pages[page - 1].text or "该页无可用文字")
    st.subheader("2 · 向论文提问")
    st.caption("提问示例：这篇论文主要研究什么？ · 实验条件是什么？ · 作者得出了什么结论？")
    st.caption("仅查原文时，请加入论文中的英文关键词，例如 experimental conditions；中文示例仅作提问思路引导。")
    with st.container(key="question_card"), st.form("rag_question_form"):
        question = st.text_area("针对上传论文提问", placeholder="例如：论文如何设计实验？请说明相关方法与结果。", max_chars=2000)
        if not config_error:
            st.caption("生成回答会将问题与论文相关文本发送给模型服务；核查研究范围时可能发送已解析全文。请仅使用有权分享的资料。")
        evidence_submitted = st.form_submit_button("查找原文依据", type="primary")
        use_model = st.form_submit_button("生成 AI 回答") if not config_error else False
        submitted = evidence_submitted or use_model
    if submitted:
        st.session_state.pop("rag_answer", None)
        try:
            with st.spinner("正在检索证据" + ("并生成回答…" if use_model else "…")):
                st.session_state.rag_answer = ask(index, question, config or ModelConfig(), use_model, top_k)
        except RagError as exc:
            st.error(str(exc))
    answer = st.session_state.get("rag_answer")
    if answer is None:
        return
    st.divider()
    st.subheader("3 · 查看结果")
    st.text(answer.question)
    if answer.status == "error":
        st.error(answer.message)
    elif answer.status in ("no_evidence", "insufficient"):
        st.warning(answer.message)
    else:
        st.text(answer.message)
    if answer.claims:
        st.subheader("AI 回答")
    for n, claim in enumerate(answer.claims, 1):
        with st.container(border=True, key=f"claim_{n}"):
            # 作为纯文本展示，避免模型输出形成任意链接或 HTML。
            st.text(f"{n}. {claim.text}")
            with st.expander("核对引用"):
                for citation in claim.citations:
                    e = citation.evidence
                    st.text(f"[{e.label}] {e.chunk.document_name} · PDF 第 {e.chunk.page} 页")
                    st.text("原文摘录：" + citation.quote)
    if answer.evidence:
        st.subheader("原文依据")
        st.caption("页码为 PDF 物理页序号。检索片段不等于答案；请结合上下文核对结论。")
        for e in answer.evidence:
            with st.container(border=True, key=f"evidence_{e.label}"):
                st.text(f"[{e.label}] {e.chunk.document_name} · 第 {e.chunk.page} 页")
                st.text(e.chunk.text)
        with st.expander("检索详情"):
            st.caption("相似度只用于检索排序，不代表答案正确概率。")
            for e in answer.evidence:
                st.text(f"[{e.label}] 相似度 {e.score:.3f}")
