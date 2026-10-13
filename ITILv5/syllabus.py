"""
syllabus.py — Map ITIL 5 Foundation syllabus codes to human-readable
Chinese topic names.

Built from the textbook TOC (page 7 of the official Chinese book).
Codes are 3-level in the rationale PDFs (e.g. "1.2.4") but the
official TOC has chapter.section names only. We map the 3-level code
to its chapter.section title; if missing, fall back to chapter title.

Syllabus layout (built from official book):
  1 介绍
    1.1 演进中的 IT 服务管理
    1.2 关于 ITIL
    ...
  2 ITIL 产品和服务管理的四个维度
    2.1-2.5
  3 数字化产品和服务管理的关键概念
    3.1 服务经济
    3.2 服务关系
  4 ITIL 产品和服务生命周期模型
    4.1-4.9
  5 ITIL 价值体系
    5.1-5.7
  6 价值流
    6.1-6.4
  7 持续改进
    7.1-7.3
"""
from __future__ import annotations

import fitz
import re
from pathlib import Path

# Source: page 7 of the textbook (TOC) + chapter list at the top.
# We keep it as a literal map rather than re-parsing the PDF every
# time so a textbook-version bump is a one-line edit.
_CHAPTERS: dict[str, str] = {
    "1": "介绍",
    "2": "ITIL 产品和服务管理的四个维度",
    "3": "数字化产品和服务管理的关键概念",
    "4": "ITIL 产品和服务生命周期模型",
    "5": "ITIL 价值体系",
    "6": "价值流",
    "7": "持续改进",
}

_SECTIONS: dict[str, str] = {
    "1.1": "演进中的 IT 服务管理",
    "1.2": "关于 ITIL",
    "1.3": "ITIL 关键概念:介绍",
    "1.4": "官方手册结构",
    "1.5": "ITIL 汽车租赁公司场景",
    "2.1": "介绍",
    "2.2": "组织和人员",
    "2.3": "价值流和流程",
    "2.4": "信息和技术",
    "2.5": "合作伙伴和供应商",
    "3.1": "服务经济",
    "3.2": "服务关系",
    "4.1": "ITIL 产品和服务生命周期及生命周期管理活动",
    "4.2": "发现",
    "4.3": "设计",
    "4.4": "获取",
    "4.5": "构建",
    "4.6": "转换",
    "4.7": "运营",
    "4.8": "交付",
    "4.9": "支持",
    "5.1": "ITIL 价值体系简介",
    "5.2": "ITIL 指导原则",
    "5.3": "治理",
    "5.4": "价值链",
    "5.5": "实践",
    "5.6": "持续改进",
    "5.7": "总结",
    "6.1": "为什么需要价值流",
    "6.2": "数字化组织的价值流",
    "6.3": "价值流映射",
    "6.4": "价值流管理",
    "7.1": "改进组织",
    "7.2": "提升专业能力",
    "7.3": "不止 ITIL",
}


def lookup(code: str) -> str:
    """Map a syllabus code (e.g. "1.2.4") to a human-readable topic.

    Returns the most specific ancestor we know. Falls back to chapter
    title if the 3rd level section isn't mapped.
    """
    if not code:
        return ""
    parts = code.split(".")
    # Try 2-level first ("1.2")
    if len(parts) >= 2:
        key2 = f"{parts[0]}.{parts[1]}"
        if key2 in _SECTIONS:
            return _SECTIONS[key2]
    # Fall back to chapter ("1")
    if parts[0] in _CHAPTERS:
        return _CHAPTERS[parts[0]]
    return ""


def format(code: str) -> str:
    """Lookup + format as 'X.Y §name' or '§chapter'."""
    name = lookup(code)
    if not name:
        return code
    parts = code.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]} {name}"
    return f"§ {name}"


# Optional: parse the TOC fresh from the PDF if you don't trust the
# literal map. Kept as opt-in — only called from scripts/, never at
# webapp boot.
def parse_toc_from_pdf(pdf_path: Path) -> dict[str, str]:
    """Re-parse the textbook TOC and return a {code: name} map.

    Used by scripts/parse_sample_papers.py when verifying against the
    actual textbook — defensive against textbook-version drift.
    """
    pdf = fitz.open(pdf_path)
    toc_text = ""
    for i in range(min(10, len(pdf))):
        toc_text += pdf[i].get_text() + "\n---\n"
    pdf.close()

    section_re = re.compile(r"^\s*(\d+)\.(\d+)\s+([^\d].+)$", re.MULTILINE)
    out: dict[str, str] = {}
    for m in section_re.finditer(toc_text):
        code = f"{m.group(1)}.{m.group(2)}"
        name = m.group(3).strip()
        if "目录" not in name and "图" not in name and "表" not in name \
                and "章节" not in name and "欢迎" not in name:
            out[code] = name
    return out