#!/usr/bin/env python3
"""
parse_sample_papers.py — Extract questions from the official ITIL 5
Foundation sample papers into questions.json.

Sources:
  ITIL_FND_官方考试样题_中文版/
    ITIL_FND_SP1_ZH_v5.0.pdf         (40 questions)
    ITIL_FND_SP1_Rationales_ZH_v5.0.pdf  (answers + explanations)
    ITIL_FND_SP2_ZH_v5.0.pdf         (40 questions)
    ITIL_FND_SP2_Rationales_ZH_v5.0.pdf  (answers + explanations)

Output:
  ../questions.json — array of {id, topic, stem, options, correct, rationale}

Question layout (SPx PDFs):
    1.                                                <- question number
    <question stem text spanning multiple lines>
    A. <option text>
    B. <option text>
    C. <option text>
    D. <option text>
    2.                                                <- next question

Rationale layout (Rationales PDFs):
    <qnum> <correct_letter> <criteria_code>
    A. 不正确/正确 ...   <- explanation for option A
    B. ...
    ...

Topic is left empty — ITIL 5 syllabus codes (e.g. 1.2.4) appear in the
rationales PDF but require a separate syllabus map to translate into
human-readable topics. Phase 3 if needed.

Run:
  .venv/bin/python scripts/parse_sample_papers.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz  # pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC_DIR = ROOT / "ITIL_FND_官方考试样题_中文版"
OUT = ROOT / "questions.json"

# Import syllabus code → topic map (sys.path tweak: parse_sample_papers.py
# lives in ITILv5/scripts/, so we add the parent so `import syllabus` works).
sys.path.insert(0, str(ROOT))
import syllabus  # noqa: E402


_QNUM_RE = re.compile(r"^\s*(\d{1,2})\.\s*$")
_OPT_RE = re.compile(r"^([A-D])\.\s*(.+)$", re.MULTILINE)
# The rationale PDF table header can be either single-line
# ("27 A 3.2.8") or multi-line (each cell on its own line, separated
# by blank lines). Normalize the multi-line form to single-line so the
# regex below matches both layouts.
_RATIONALE_QNUM_RE = re.compile(
    r"^\s*(\d{1,2})[ \t]+([A-D])[ \t]+([\d.]+)\s*$",
    re.MULTILINE,
)


def _collapse_qnum_blocks(text: str) -> str:
    """Replace each 'qnum / blank / letter / blank / code / blank'
    block with a single-line 'qnum letter code' entry."""
    block_re = re.compile(
        r"^\s*(\d{1,2})\s*\n\s*([A-D])\s*\n\s*([\d.]+)\s*\n",
        re.MULTILINE,
    )
    return block_re.sub(r"\1 \2 \3\n", text)
_LETTER_HEAD_RE = re.compile(r"^([A-D])\.\s*(.+)$")


def extract_questions_from_text(text: str) -> list[dict]:
    """Walk the raw page text and pull out questions with options.

    Returns a list of dicts: {qnum, stem, options: {A:..., B:..., C:..., D:...}}.
    Returns empty list if the page contains no questions (e.g. cover, instructions).

    State machine:
      - "N." alone on a line → start a new question
      - before first option letter seen → append to stem
      - on "A./B./C./D." → start a new option (don't touch stem)
      - after options started → append to most-recent option
    """
    # Drop page-header footer noise
    text = re.sub(r"^\d+\s*\n", "", text, flags=re.MULTILINE)  # page numbers
    text = re.sub(
        r"^ITIL® 基础 \| 样本试卷.*$\n?",
        "",
        text,
        flags=re.MULTILINE,
    )

    lines = text.splitlines()
    questions: list[dict] = []
    cur: dict | None = None

    for line in lines:
        stripped = line.strip()
        m_q = _QNUM_RE.match(line)
        m_opt = _LETTER_HEAD_RE.match(line)

        if m_q and not stripped[m_q.end():].strip():
            # Pure "N." line — start of a new question
            if cur is not None:
                questions.append(cur)
            cur = {"qnum": int(m_q.group(1)), "stem": "", "options": {}}
            continue
        if cur is None:
            continue

        if m_opt and m_opt.group(1) in {"A", "B", "C", "D"}:
            letter = m_opt.group(1)
            cur["options"][letter] = m_opt.group(2).strip()
            continue

        # Otherwise: text line. Append to stem if no options yet,
        # else append to the most recently seen option.
        if not cur["options"]:
            cur["stem"] += ("\n" if cur["stem"] else "") + stripped
        else:
            last_letter = next(reversed(cur["options"]))
            cur["options"][last_letter] += "\n" + stripped

    if cur is not None:
        questions.append(cur)

    # Cleanup: trim whitespace, drop questions missing any option
    cleaned: list[dict] = []
    for q in questions:
        q["stem"] = q["stem"].strip()
        for k, v in list(q["options"].items()):
            q["options"][k] = v.strip()
        if len(q["options"]) == 4 and all(q["options"].values()):
            cleaned.append(q)
    return cleaned


def extract_rationales_from_text(text: str) -> dict[int, dict]:
    """Walk rationale PDF text and pull out {qnum: {correct, code, rationale}}.

    Each entry has the form:
        <qnum> <correct_letter> <syllabus_code>
        A. 不正确 ... \n B. 不正确 ... \n C. 正确 ... \n D. 不正确 ...

    The PDF lays out the qnum/letter/code header in EITHER:
      - single-line ("27 A 3.2.8"), or
      - multi-line ("27\n\nA\n\n\n3.2.8\n")
    We collapse the multi-line form to single-line first, then parse.

    Note: rationale text often spans multiple pages (A on page N, C+D on
    page N+1). We concatenate per-page text in the caller and parse the
    whole thing as one stream, so cross-page entries are captured
    correctly. (Earlier we did per-page parsing + dict.update, which
    silently overwrote the first page's body with the second page's.)
    """
    text = _collapse_qnum_blocks(text)
    rationales: dict[int, dict] = {}
    matches = list(_RATIONALE_QNUM_RE.finditer(text))
    for i, m in enumerate(matches):
        qnum = int(m.group(1))
        correct = m.group(2)
        code = m.group(3)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        rationales[qnum] = {"correct": correct, "code": code, "rationale": body}
    return rationales


def parse_paper(
    q_pdf: Path,
    r_pdf: Path,
    paper_id: str,
) -> list[dict]:
    """Parse one (questions, rationales) PDF pair into a question list."""
    print(f"[parse] reading {q_pdf.name}")
    q_doc = fitz.open(q_pdf)
    all_qs: dict[int, dict] = {}
    for page in q_doc:
        qs = extract_questions_from_text(page.get_text())
        for q in qs:
            if q["qnum"] in all_qs:
                # Multi-page question — merge stem/options
                existing = all_qs[q["qnum"]]
                if not existing["stem"].endswith(q["stem"]):
                    existing["stem"] += "\n" + q["stem"]
                for k, v in q["options"].items():
                    if v and not existing["options"].get(k):
                        existing["options"][k] = v
                    elif v and existing["options"].get(k) and existing["options"][k] != v:
                        existing["options"][k] += "\n" + v
            else:
                all_qs[q["qnum"]] = q
    q_doc.close()

    print(f"[parse] reading {r_pdf.name}")
    r_doc = fitz.open(r_pdf)
    # Concatenate all page text first, then parse as one stream —
    # rationale bodies span pages, and per-page dict.update silently
    # overwrites them (only keeps the last page's text for each qnum).
    r_full_text = ""
    for page in r_doc:
        r_full_text += page.get_text() + "\n"
    r_doc.close()
    all_r = extract_rationales_from_text(r_full_text)

    # Merge into final schema
    out: list[dict] = []
    for qnum in sorted(all_qs.keys()):
        q = all_qs[qnum]
        r = all_r.get(qnum, {})
        if not r:
            print(f"[parse] WARN: q{qnum} missing rationale", file=sys.stderr)
        code = r.get("code", "")
        # Map code → human-readable topic via syllabus.py
        topic = syllabus.format(code) if code else ""
        out.append({
            "id": f"{paper_id}-q{qnum:02d}",
            "topic": topic,
            "syllabus_code": code,  # keep raw too for debugging / future use
            "stem": q["stem"],
            "options": q["options"],
            "correct": r.get("correct", ""),
            "rationale": r.get("rationale", ""),
        })
    return out


def main() -> None:
    if not SRC_DIR.exists():
        print(f"[parse] FATAL: source dir missing: {SRC_DIR}", file=sys.stderr)
        sys.exit(1)
    all_q: list[dict] = []
    for paper_id, q_name, r_name in [
        ("sp1", "ITIL_FND_SP1_ZH_v5.0.pdf", "ITIL_FND_SP1_Rationales_ZH_v5.0.pdf"),
        ("sp2", "ITIL_FND_SP2_ZH_v5.0.pdf", "ITIL_FND_SP2_Rationales_ZH_v5.0.pdf"),
    ]:
        all_q.extend(parse_paper(SRC_DIR / q_name, SRC_DIR / r_name, paper_id))

    # Load existing questions.json (so we don't clobber manual additions).
    existing: list[dict] = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = []
    existing_by_id = {q["id"]: q for q in existing}

    # Two-pass merge:
    #  - update existing entries (topic, syllabus_code) with the
    #    freshly-extracted values
    #  - add new entries
    updated = 0
    new_count = 0
    for q in all_q:
        if q["id"] in existing_by_id:
            old = existing_by_id[q["id"]]
            for field in ("topic", "syllabus_code", "correct", "rationale"):
                if q.get(field) and q[field] != old.get(field):
                    old[field] = q[field]
                    updated += 1
        else:
            existing.append(q)
            new_count += 1

    OUT.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[parse] wrote {new_count} new, {updated} field updates, "
        f"{len(existing)} total → {OUT}"
    )
    if new_count:
        print(f"[parse] sample new id: {existing[-new_count]['id']}")
    # Print topic coverage
    with_topic = sum(1 for q in existing if q.get("topic"))
    print(f"[parse] topics filled: {with_topic}/{len(existing)}")


if __name__ == "__main__":
    main()