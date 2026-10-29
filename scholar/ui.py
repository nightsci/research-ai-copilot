"""中文界面只负责交互；数据处理逻辑留在独立模块。"""
from datetime import datetime
from zoneinfo import ZoneInfo
import html
import os
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
from scholar.processing import export_csv, filter_papers
from scholar.service import search_papers
from scholar.presentation import apply_style


def setting(name: str) -> str:
    if os.getenv(name):
        return os.environ[name]
    try:
        return str(st.secrets.get(name, ""))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return ""


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    st.set_page_config(page_title="Research AI Copilot", page_icon=":material/menu_book:",
                       layout="wide", initial_sidebar_state="auto")
    apply_style()
    # 保留导航状态 key，并迁移旧版本会话中的页面名称。
    previous = st.session_state.get("feature_page")
    if previous in ("多源学术检索", "科研 AI 智能问答"):
        st.session_state.feature_page = {"多源学术检索": "文献检索", "科研 AI 智能问答": "论文阅读"}[previous]
    with st.container(key="workspace"):
        with st.container(key="brand"):
            st.title("Research AI Copilot")
            st.caption("科研文献智能工作台")
        page = st.radio("工作台导航", ["文献检索", "论文阅读"], horizontal=True,
                        key="feature_page", label_visibility="collapsed")
        if page == "论文阅读":
            from rag.ui import render_rag
            render_rag(setting)
        else:
            render_scholar()


def render_scholar():
    st.header("探索学术文献")
    st.write("跨平台检索研究成果，轻松整理你的阅读清单。")
    with st.sidebar:
        st.subheader("检索范围")
        sources = st.multiselect("数据来源", ["OpenAlex", "Crossref"], default=["OpenAlex", "Crossref"])
        with st.expander("更多设置"):
            limit = st.select_slider("每个来源最多取回", options=[10, 25, 50, 100], value=25)
            st.caption("仅检索各来源的前 N 条相关记录，不代表数据库全部匹配结果。")

    with st.container(key="search_card"), st.form("search_form"):
        mode = st.radio("检索方式", ["关键词搜索", "DOI 查询"], horizontal=True)
        query = st.text_input("研究主题或 DOI", value="", placeholder="例如 polysilazane corrosion coating 或 10.xxxx/xxxxx")
        with st.expander("高级筛选"):
            use_year = st.checkbox("限定发表年份", value=False)
            left, right = st.columns(2)
            current_year = datetime.now(ZoneInfo("Asia/Shanghai")).year
            start = left.number_input("起始年份", 1600, current_year + 1, 2000)
            end = right.number_input("结束年份", 1600, current_year + 1, current_year)
        submitted = st.form_submit_button("开始检索", type="primary", use_container_width=True)
    if submitted:
        # 清除上一轮，避免失败时把旧结果误认为新结果。
        st.session_state.pop("search_result", None)
        try:
            with st.spinner("正在查询真实学术 API，请稍候…"):
                result = search_papers(query, tuple(sources), limit,
                                       int(start) if use_year else None, int(end) if use_year else None,
                                       mode == "DOI 查询", setting("OPENALEX_API_KEY"), setting("CROSSREF_MAILTO"))
            st.session_state.search_result = result
            st.session_state.search_info = (query, int(start) if use_year else None,
                                            int(end) if use_year else None,
                                            datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"))
            st.session_state["journal_filter"] = ""
        except ValueError as exc:
            st.error(str(exc))

    result = st.session_state.get("search_result")
    if result is None:
        st.caption("输入研究主题，开始探索相关文献。")
        return
    searched, start, end, searched_at = st.session_state.search_info
    st.divider()
    st.write(f"本次查询：{searched}")
    st.caption(f"查询时间：{searched_at}（北京时间） · 修改检索条件后请重新点击开始检索。")
    for source, error in result.errors.items():
        # 来源错误仍明确告知访客，但把部署操作留给维护者。
        friendly_error = error.replace("请检查 API key、账户状态或网络访问权限", "请稍后重试或联系维护者")
        friendly_error = friendly_error.replace("；OpenAlex 可配置自己的 API key", "")
        st.warning(f"{source}：{friendly_error}")
    journal = st.text_input("期刊筛选（仅筛选本次取回结果，支持名称片段）", key="journal_filter",
                            placeholder="例如 Surface 或 Corrosion")
    papers = filter_papers(result.papers, start, end, journal)
    col1, col2, col3 = st.columns(3)
    col1.metric("本次检索总数", sum(result.counts.values()))
    col2.metric("合并去重后", len(result.papers))
    col3.metric("当前显示", len(papers))
    st.caption("数量仅代表本次取回记录；论文链接通往来源网站，全文可能需要订阅。")
    if not papers:
        if result.errors and not result.counts:
            st.error("所有来源均未成功，请检查网络或凭据后重试。")
        else:
            st.info("本次没有符合条件的记录。可放宽年份、清空期刊筛选或增加取回数量。")
        return
    st.download_button("导出 CSV", export_csv(papers), "scholar-results.csv", "text/csv", icon=":material/download:")
    for index, paper in enumerate(papers, 1):
        with st.container(border=True, key=f"paper_{index}"):
            # 标题先转义，再加入少量固定 HTML；不信任接口返回的标记。
            st.markdown(f"<h3>{index:02d} · {html.escape(paper.title or '标题未提供')}</h3>", unsafe_allow_html=True)
            st.text("作者：" + ("；".join(paper.authors) or "未提供"))
            st.text(f"{paper.year or '年份未提供'} · {paper.journal or '期刊未提供'}")
            st.text("来源：" + " + ".join(paper.sources))
            if paper.url:
                st.link_button("查看论文", paper.url, icon=":material/open_in_new:")
            with st.expander("DOI 与来源记录"):
                st.text("DOI：" + (paper.doi or "未提供"))
                for i, url in enumerate(paper.source_urls[:2], 1):
                    st.link_button(f"来源记录 {i}", url)
