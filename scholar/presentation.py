"""轻量展示样式；不接触查询、模型或会话业务数据。"""
import streamlit as st


def apply_style():
    # 仅固定 CSS：不插入用户输入，使用自有 key 与语义元素，不依赖生成类名。
    st.html("""<style>
    h1 { letter-spacing: -.035em; font-size: 2.3rem !important; }
    h2 { letter-spacing: -.02em; font-size: 1.8rem !important; }
    h3 { font-size: 1.25rem !important; }
    .st-key-workspace { max-width: 1120px; margin-inline: auto; }
    .st-key-feature_page label { padding: .55rem 1rem; border-radius: .7rem;
      background: white; border: 1px solid #dce7e8; cursor: pointer; }
    .st-key-feature_page label:has(input:checked) {
      background: #e3f3f0; border-color: #137c78; color: #115e59; }
    .st-key-feature_page [role="radiogroup"] { gap: .5rem; }
    .st-key-brand { border-bottom: 1px solid #dce7e8; padding-bottom: .7rem; }
    .st-key-search_card, .st-key-question_card { background: white; border-radius: .75rem; }
    [class*="st-key-paper_"], [class*="st-key-evidence_"], [class*="st-key-claim_"] {
      background: white; border-radius: .75rem; }
    p, pre { overflow-wrap: anywhere; }
    @media (max-width: 640px) {
      h1 { font-size: 1.8rem !important; }
      h2 { font-size: 1.4rem !important; }
      .st-key-feature_page label { padding: .45rem .65rem; }
    }
    </style>""")
