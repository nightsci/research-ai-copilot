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
    st.caption("RESEARCH AI COPILOT / 论文阅读")
    st.title("📄 科研 AI 智能问答")
    st.write("上传论文，定位原文证据与页码；模型可用时可进一步生成带引用的回答。")
    st.caption("支持带文字层的 PDF；每个文件最多 20 MB、200 页，最多 3 个文件。页码指 PDF 物理页序号。")
    config = None
    config_error = ""
    try:
        config = read_config(setting)
        config.validate()
    except RagError as exc:
        config_error = str(exc)
    evidence_only = config is not None and not config.api_key
    if evidence_only:
        st.info("当前为原文证据模式：可上传 PDF、提取文字、检索原文并查看来源页码。"
                "本站未启用模型密钥，生成式 AI 回答及模型翻译暂未开放，这是演示设置，并非功能故障。")
        st.caption("DeepSeek 中文问答、跨语言改写和引用校验已在本地真实调用中验证。"
                   "阅读英文论文时，请在问题中加入论文使用的英文关键词；当前返回原文片段，不会生成答案。")
    elif config_error:
        st.warning("模型暂不可用，仍可上传 PDF 和检索原文证据。")
    with st.sidebar:
        st.header("科研问答设置")
        if config_error:
            st.info(config_error)
        else:
            st.success("模型接口已配置（尚未验证连接）")
        st.caption("凭据从环境变量或 Streamlit Secrets 读取。配置方法见 README。")
        top_k = st.slider("最多检索片段数", 1, 8, 5, key="rag_top_k")
        st.caption("文档、索引和本次回答仅保存在当前会话内；服务器重启后需重新上传。")

    files = st.file_uploader("上传真实 PDF 论文", type=["pdf"], accept_multiple_files=True, key="rag_uploads")
    manifest = tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in (files or []))
    if st.session_state.get("rag_manifest") != manifest:
        clear_documents()
        st.session_state.rag_manifest = manifest
    if st.button("提取文字并建立索引", type="primary", disabled=not files):
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
        st.info("请上传 PDF 并建立索引。没有模型密钥也可以完成文字提取和证据检索。")
        return
    index = st.session_state.rag_index
    st.success(f"已就绪：{len(docs)} 篇文档，{sum(len(d.pages) for d in docs)} 页，{len(index.chunks)} 个片段。")
    for doc in docs:
        with st.expander(f"查看提取文本 · {doc.name} · {doc.id[:8]}"):
            if doc.empty_pages:
                st.warning("这些页面未提取到足够文字（可能是扫描页、空白页或图片页），未进入检索：" + ", ".join(map(str, doc.empty_pages)))
            page = st.selectbox("预览物理页", [p.number for p in doc.pages], key=f"preview_{doc.id}")
            st.text(doc.pages[page - 1].text or "该页无可用文字")
    st.caption("启用模型后，中文问题会先翻译为英文检索英文论文，再用原问题生成回答。仅查证据或无密钥时，请加入英文关键词。")
    with st.form("rag_question_form"):
        question = st.text_area("针对上传论文提问", placeholder="例如：论文如何设计实验？请说明相关方法与结果。", max_chars=2000)
        use_model = st.checkbox("调用模型生成回答", value=False, disabled=bool(config_error))
        st.caption("启用生成后，问题及最多 8 个片段会发送给模型服务。跨语言改写会额外调用一次模型；核查论文是否涉及某主题时，可能发送已提取全文（最多 90000 字符）。不上传 PDF 文件本身。")
        submitted = st.form_submit_button("检索原文证据" if config_error else "检索并回答", type="primary")
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
    st.subheader("本次问题")
    st.text(answer.question)
    if answer.trace:
        with st.expander("检索调试（仅当前会话）"):
            st.json(answer.trace)
    if answer.status == "error":
        st.error(answer.message)
    elif answer.status in ("no_evidence", "insufficient"):
        st.warning(answer.message)
    else:
        st.info(answer.message)
    for n, claim in enumerate(answer.claims, 1):
        with st.container(border=True):
            # 作为纯文本展示，避免模型输出形成任意链接或 HTML。
            st.text(f"{n}. {claim.text}")
            for citation in claim.citations:
                e = citation.evidence
                st.caption(f"[{e.label}] {e.chunk.document_name} · PDF 第 {e.chunk.page} 页 · {e.chunk.document_id[:8]}")
                st.text("原文摘录：" + citation.quote)
    if answer.evidence:
        st.subheader("实际检索到的原文")
        st.caption("相似度用于排序，不代表答案正确概率。引用校验只能证明摘录存在，结论是否受支持仍需阅读原文核对。")
        for e in answer.evidence:
            with st.expander(f"[{e.label}] {e.chunk.document_name} · 第 {e.chunk.page} 页 · 相似度 {e.score:.3f}"):
                st.text(e.chunk.text)
                st.caption(f"文档 {e.chunk.document_id[:8]}；该页提取文本字符区间 {e.chunk.start}–{e.chunk.end}")
