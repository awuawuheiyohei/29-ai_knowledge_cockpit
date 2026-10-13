"""
ITIL 5 Foundation 刷题 web app (skeleton).

Phase 1 (this file):
  - Flask backend on port 5002
  - SQLite-backed questions + attempts
  - 4 endpoints: health / question / answer / stats
  - Single-page SPA served from templates/index.html

Phase 2 (later):
  - PDF parser for ITIL_FND_官方考试样题_中文版/ (SP1 + SP2)
  - Topic categorization
  - Wrong book + mastery tracking
  - Random option shuffle

Run (from this directory, no absolute paths needed):
  ../.venv/bin/python app.py
  # or: make up
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Reuse the ai_knowledge_cockpit venv (Flask already installed there)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, g, jsonify, render_template, request  # noqa: E402

HERE = Path(__file__).resolve().parent
QUESTIONS_JSON = HERE / "questions.json"
DB_PATH = HERE / "exam.sqlite"
PORT = 5002  # CISSP exam is on 5001; keep separate

# Cookie name + TTL for stable stats across page reloads / new tabs.
SESSION_COOKIE = "itil_sid"
SESSION_TTL_S = 30 * 24 * 3600  # 30 days


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Create tables + seed from questions.json if empty."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL DEFAULT '',
                stem TEXT NOT NULL,
                options_json TEXT NOT NULL,   -- {"A": "...", ...}
                correct TEXT NOT NULL,        -- "A" | "B" | "C" | "D"
                rationale TEXT NOT NULL DEFAULT '',
                syllabus_code TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qid TEXT NOT NULL,
                answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,  -- 0 | 1
                session TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_attempts_session
                ON attempts(session);
            CREATE INDEX IF NOT EXISTS idx_attempts_qid
                ON attempts(qid);
        """)
        conn.commit()
        # Backfill syllabus_code on DBs created before the column existed
        # (CREATE TABLE IF NOT EXISTS won't add it to an existing table).
        cols = {
            r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()
        }
        if "syllabus_code" not in cols:
            conn.execute("ALTER TABLE questions ADD COLUMN syllabus_code TEXT NOT NULL DEFAULT ''")
            conn.commit()
        # Seed from questions.json if table empty
        existing = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        if existing == 0 and QUESTIONS_JSON.exists():
            data = json.loads(QUESTIONS_JSON.read_text(encoding="utf-8"))
            for q in data:
                conn.execute(
                    "INSERT INTO questions(id, topic, stem, options_json, correct, "
                    "rationale, syllabus_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        q["id"],
                        q.get("topic", ""),
                        q["stem"],
                        json.dumps(q["options"], ensure_ascii=False),
                        q["correct"],
                        q.get("rationale", ""),
                        q.get("syllabus_code", ""),
                    ),
                )
            conn.commit()
        # Backfill syllabus_code for rows seeded before the column landed.
        if QUESTIONS_JSON.exists():
            for q in json.loads(QUESTIONS_JSON.read_text(encoding="utf-8")):
                conn.execute(
                    "UPDATE questions SET syllabus_code = ? WHERE id = ? "
                    "AND (syllabus_code IS NULL OR syllabus_code = '')",
                    (q.get("syllabus_code", ""), q["id"]),
                )
            conn.commit()
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30.0)
        g.db.row_factory = sqlite3.Row
    return g.db


app = Flask(__name__, template_folder=str(HERE / "templates"))


@app.teardown_appcontext
def _close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.before_request
def _ensure_session() -> None:
    """Pull a per-browser session id from the cookie (set on first
    response). Previous implementation used timestamp, which meant
    every request got a new "session" and stats were always 0."""
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        # Generate one now; after_request hook will persist it as a
        # cookie so the same browser keeps the same id next time.
        sid = uuid.uuid4().hex[:12]
        g.sid_new = True
    else:
        g.sid_new = False
    g.sid = sid


@app.after_request
def _persist_session(resp):
    """If we minted a new sid this request, set the cookie so future
    requests in this browser reuse it."""
    if getattr(g, "sid_new", False):
        resp.set_cookie(
            SESSION_COOKIE, g.sid,
            max_age=SESSION_TTL_S,
            samesite="Lax",
        )
    return resp


def _session_id() -> str:
    return g.sid


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    return jsonify(ok=True, questions=total, port=PORT, phase=1)


@app.route("/api/question", methods=["GET"])
def api_question():
    """Return a random question for this session.

    Modes:
      - (default)   : any unanswered question (current behaviour)
      - mode=wrong  : only questions this session has previously
                      answered incorrectly (the "错题本" pool)
      - mode=all    : any question, even answered ones

    Falls back gracefully — e.g. wrong mode + no wrong answers left
    returns 404 so the SPA can switch modes.
    """
    db = get_db()
    sid = _session_id()
    mode = request.args.get("mode", "default")

    if mode == "wrong":
        # Wrong-book pool: qids this session got wrong on their most
        # recent attempt. We pick MAX(created_at) per qid so a
        # corrected retry drops the qid from the pool.
        wrong_rows = db.execute("""
            SELECT q.id, q.topic, q.stem, q.options_json, q.syllabus_code
            FROM questions q
            WHERE q.id IN (
              SELECT qid FROM attempts
              WHERE session = ?
              GROUP BY qid
              HAVING MAX(is_correct) = 0
            )
            ORDER BY RANDOM() LIMIT 1
        """, (sid,)).fetchall()
        if not wrong_rows:
            return jsonify(error="no wrong questions in this session"), 404
        row = wrong_rows[0]
    else:
        answered = {
            r["qid"]
            for r in db.execute(
                "SELECT qid FROM attempts WHERE session = ?", (sid,)
            ).fetchall()
        }
        rows = db.execute(
            "SELECT id, topic, stem, options_json, syllabus_code "
            "FROM questions ORDER BY RANDOM() LIMIT 1"
        ).fetchall()
        # In "default" mode prefer unanswered; in "all" mode allow any.
        if mode == "all":
            row = rows[0] if rows else None
        else:
            row = next((r for r in rows if r["id"] not in answered), rows[0] if rows else None)
        if row is None:
            return jsonify(error="no questions in bank"), 404

    return jsonify(
        id=row["id"],
        topic=row["topic"],
        stem=row["stem"],
        options=json.loads(row["options_json"]),
        syllabus_code=row["syllabus_code"],
        # DO NOT return `correct` or `rationale` — those are gated
        # behind /api/answer.
    )


@app.route("/api/answer", methods=["POST"])
def api_answer():
    """Submit an answer; return correctness + correct option + rationale."""
    body = request.get_json(silent=True) or {}
    qid = body.get("qid", "")
    chosen = body.get("answer", "").strip().upper()
    if not qid or chosen not in {"A", "B", "C", "D"}:
        return jsonify(error="invalid payload"), 400
    db = get_db()
    q = db.execute(
        "SELECT correct, rationale FROM questions WHERE id = ?", (qid,)
    ).fetchone()
    if q is None:
        return jsonify(error=f"unknown question: {qid}"), 404
    is_correct = 1 if chosen == q["correct"] else 0
    db.execute(
        "INSERT INTO attempts(qid, answer, is_correct, session, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (qid, chosen, is_correct, _session_id(), _now()),
    )
    db.commit()
    return jsonify(
        qid=qid,
        chosen=chosen,
        correct=q["correct"],
        is_correct=bool(is_correct),
        rationale=q["rationale"],
    )


@app.route("/api/stats", methods=["GET"])
def api_stats():
    db = get_db()
    sid = _session_id()
    total = db.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    answered, correct = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(is_correct), 0) "
        "FROM attempts WHERE session = ?",
        (sid,),
    ).fetchone()
    answered = answered or 0
    correct = correct or 0
    # Wrong-book size: distinct questions whose most recent attempt
    # in this session was incorrect.
    wrong_count = db.execute("""
        SELECT COUNT(*) FROM (
          SELECT qid FROM attempts
          WHERE session = ?
          GROUP BY qid
          HAVING MAX(is_correct) = 0
        )
    """, (sid,)).fetchone()[0]
    return jsonify(
        session=sid,
        total=total,
        answered=answered,
        correct=correct,
        wrong=wrong_count,
        accuracy=(correct / answered) if answered else 0.0,
    )


@app.route("/api/wrong", methods=["GET"])
def api_wrong():
    """List all wrong questions for this session.

    Returns a list of {id, topic, stem, options} so the SPA can show
    the user a "wrong book" summary view.
    """
    db = get_db()
    sid = _session_id()
    rows = db.execute("""
        SELECT q.id, q.topic, q.stem, q.options_json
        FROM questions q
        WHERE q.id IN (
          SELECT qid FROM attempts
          WHERE session = ?
          GROUP BY qid
          HAVING MAX(is_correct) = 0
        )
        ORDER BY q.id
    """, (sid,)).fetchall()
    return jsonify(
        wrong=[
            {
                "id": r["id"],
                "topic": r["topic"],
                "stem": r["stem"],
                "options": json.loads(r["options_json"]),
            }
            for r in rows
        ],
        count=len(rows),
    )


if __name__ == "__main__":
    init_db()
    print(f"[ITILv5] questions={QUESTIONS_JSON} db={DB_PATH} port={PORT}")
    print("[ITILv5] open http://127.0.0.1:5002")
    app.run(host="127.0.0.1", port=PORT, debug=False)