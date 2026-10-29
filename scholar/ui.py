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


def setting(name: str) -> str:
    if os.getenv(name):
        return os.environ[name]
    try:
        return str(st.secrets.get(name, ""))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return ""


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    st.set_page_config(page_title="Research AI Copilot", page_icon="📚", layout="wide")
    page = st.radio("功能页面", ["多源学术检索", "科研 AI 智能问答"], horizontal=True, key="feature_page")
    if page == "科研 AI 智能问答":
        from rag.ui import render_rag
        render_rag(setting)
    else:
        render_scholar()


def render_scholar():
    st.caption("RESEARCH AI COPILOT  /  第一阶段")
    st.title("📚 Scholar Connector")
    st.markdown("### 让科研探索，从一站式文献检索开始")
    st.write("连接 OpenAlex 与 Crossref，检索真实学术记录，整合来源并导出你的阅读清单。")
    with st.sidebar:
        st.header("检索设置")
        sources = st.multiselect("数据来源", ["OpenAlex", "Crossref"], default=["OpenAlex", "Crossref"])
        limit = st.select_slider("每个来源最多取回", options=[10, 25, 50, 100], value=25)
        st.caption("仅取回每个来源的前 N 条结果；两个来源的相关性排序方式不同。")
        st.divider()
        st.markdown("**连接状态**")
        st.caption("OpenAlex：" + ("已配置 API key" if setting("OPENALEX_API_KEY") else "匿名访问"))
        st.caption("Crossref：" + ("已配置联系邮箱" if setting("CROSSREF_MAILTO") else "公共访问"))
        st.caption("可在 .env 或部署平台 Secrets 中配置凭据。")
        st.markdown("[OpenAlex](https://openalex.org) · [Crossref](https://www.crossref.org)")

    with st.form("search_form"):
        mode = st.radio("检索方式", ["关键词搜索", "DOI 查询"], horizontal=True)
        query = st.text_input("关键词或 DOI", value="polysilazane corrosion coating",
                              placeholder="输入研究主题或 10.xxxx/xxxxx")
        use_year = st.checkbox("限定发表年份", value=False)
        left, right = st.columns(2)
        current_year = datetime.now(ZoneInfo("Asia/Shanghai")).year
        start = left.number_input("起始年份", 1600, current_year + 1, 2000)
        end = right.number_input("结束年份", 1600, current_year + 1, current_year)
        st.caption("年份限制会发送给关键词检索接口；DOI 查询结果也会按年份筛选。")
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
        st.info("输入主题后点击「开始检索」。页面只展示 API 实际返回的记录。")
        return
    searched, start, end, searched_at = st.session_state.search_info
    st.divider()
    st.write(f"本次查询：{searched}")
    st.caption(f"查询时间：{searched_at}（北京时间） · 修改检索条件后请重新点击开始检索。")
    for source, error in result.errors.items():
        st.warning(f"{source}：{error}")
    for source, count in result.counts.items():
        st.caption(f"✓ {source} 已连接，本次取回 {count} 条")
    journal = st.text_input("期刊筛选（仅筛选本次取回结果，支持名称片段）", key="journal_filter",
                            placeholder="例如 Surface 或 Corrosion")
    papers = filter_papers(result.papers, start, end, journal)
    col1, col2, col3 = st.columns(3)
    col1.metric("来源返回", sum(result.counts.values()))
    col2.metric("合并去重后", len(result.papers))
    col3.metric("当前显示", len(papers))
    st.caption("去重优先匹配 DOI；缺 DOI 时匹配标题、年份和首作者。原文按钮通往出版方页面，全文可能需要订阅。")
    if not papers:
        if result.errors and not result.counts:
            st.error("所有来源均未成功，请检查网络或凭据后重试。")
        else:
            st.info("本次没有符合条件的记录。可放宽年份、清空期刊筛选或增加取回数量。")
        return
    st.download_button("↓ 导出当前结果 CSV", export_csv(papers), "scholar-results.csv", "text/csv")
    for index, paper in enumerate(papers, 1):
        with st.container(border=True):
            # 标题先转义，再加入少量固定 HTML；不信任接口返回的标记。
            st.markdown(f"<h3>{index:02d} · {html.escape(paper.title or '标题未提供')}</h3>", unsafe_allow_html=True)
            st.write("作者：" + ("；".join(paper.authors) or "未提供"))
            st.write(f"年份：{paper.year or '未提供'}　|　期刊：{paper.journal or '未提供'}")
            st.caption("数据来源：" + " + ".join(paper.sources))
            st.text("DOI：" + (paper.doi or "未提供"))
            columns = st.columns([1, 1, 1, 3])
            if paper.url:
                columns[0].link_button("打开原文 ↗", paper.url)
            for i, url in enumerate(paper.source_urls[:2], 1):
                columns[i].link_button(f"来源记录 {i} ↗", url)
