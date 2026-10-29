"""可解释的意图路由；不把检索失败当成全文未涉及的证明。"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    kind: str
    section_query: str = ""
    clarification: str = ""


def identify(question: str) -> Intent:
    q = question.lower().strip(" ？?。")
    if q in ("这个怎么样", "这个呢", "为什么", "怎么样", "解释一下", "它怎么样"):
        return Intent("ambiguous", clarification="你想了解论文的研究目的、实验方法，还是某项结果？请指出要讨论的对象。")
    if any(w in q for w in ("讲什么", "主要内容", "总结", "研究主题", "研究什么", "概括", "summarize", "summary")):
        return Intent("summary", "abstract conclusions summary objectives findings")
    if any(w in q for w in ("实验条件", "温度", "浓度", "相差多少", "多少", "数值", "数据", "conditions", "how much")):
        return Intent("data", "experimental conditions concentration temperature kinetics rate constants results")
    if any(w in q for w in ("怎么做实验", "如何实验", "实验方法", "实验怎么做", "methods", "procedure")):
        return Intent("methods", "experimental procedure methods materials instrumentation reaction monitoring")
    if any(w in q for w in ("为什么", "原因", "why", "比较", "推断")):
        return Intent("reasoning")
    return Intent("fact")


def overview(index, limit=3):
    """首片段包含标题，摘要/结论候选只用于概览或主题核查。"""
    selected = []
    seen_docs = set()
    for c in index.chunks:
        if c.document_id not in seen_docs:
            selected.append(c)
            seen_docs.add(c.document_id)
    for c in index.chunks:
        if re.search(r"\b(abstract|conclusions?)\b|摘要|结论", c.text, re.I) and c not in selected:
            selected.append(c)
    return selected[:limit]
