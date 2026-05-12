#!/usr/bin/env python3
"""Nightly learner — ingests closed trades and retrains the scorer.

Pipeline (idempotent, safe to re-run):
1. Load trade_history/{today}.json (fallback to most recent available).
2. For each closed trade with a clear exit_reason, extract market features
   at the entry timestamp via features.extract_features.
3. Append features + outcome to learning.db (SQLite). Unique by position_id.
4. Invoke mt5_auto_tuner.py to adjust risk_config.json.
5. If >= MIN_SAMPLES_TO_TRAIN cumulative samples: retrain
   RandomForestClassifier, pickle it, record cv_score in model_versions.
6. Print a short report (useful as a cron stdout that can be forwarded
   to Telegram).
"""

from __future__ import annotations

import io
import json
import pickle
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

SKILL_DIR = Path(__file__).resolve().parents[1]
HISTORY_DIR = SKILL_DIR / "trade_history"
DB_PATH = SKILL_DIR / "learning.db"
MODELS_DIR = SKILL_DIR / "models"
AUTO_TUNER = SKILL_DIR / "scripts" / "mt5_auto_tuner.py"

sys.path.insert(0, str(SKILL_DIR))
try:
    from features import extract_features, FEATURE_COLUMNS
except Exception as e:  # noqa: BLE001
    print(f"WARNING: cannot import features module: {e}")
    extract_features = None
    FEATURE_COLUMNS = []

MIN_SAMPLES_TO_TRAIN = 30


def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS features (
            position_id INTEGER PRIMARY KEY,
            entry_ts TEXT NOT NULL,
            side TEXT NOT NULL,
            features_json TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'live',
            inserted_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS outcomes (
            position_id INTEGER PRIMARY KEY,
            won INTEGER NOT NULL,
            net_profit REAL NOT NULL,
            duration_min REAL NOT NULL,
            exit_reason TEXT NOT NULL,
            FOREIGN KEY(position_id) REFERENCES features(position_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS model_versions (
            version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trained_at TEXT NOT NULL,
            n_samples INTEGER NOT NULL,
            cv_score REAL,
            model_path TEXT NOT NULL,
            features_used TEXT NOT NULL,
            notes TEXT
        )
    """)
    conn.commit()


def load_today_json():
    today = datetime.now().strftime("%Y-%m-%d")
    today_path = HISTORY_DIR / f"{today}.json"
    if today_path.exists():
        try:
            return json.loads(today_path.read_text(encoding="utf-8")), today_path.name
        except json.JSONDecodeError:
            pass
    candidates = sorted(HISTORY_DIR.glob("[0-9][0-9][0-9][0-9]-*.json"))
    if not candidates:
        return None, None
    latest = candidates[-1]
    try:
        return json.loads(latest.read_text(encoding="utf-8")), latest.name
    except json.JSONDecodeError:
        return None, None


def ingest_trades(conn: sqlite3.Connection, data: dict) -> dict:
    stats = {"considered": 0, "ingested": 0, "skipped_manual": 0,
             "skipped_existing": 0, "skipped_no_features": 0}
    if extract_features is None:
        return stats
    cur = conn.cursor()
    for t in data.get("trades", []):
        stats["considered"] += 1
        if not t.get("is_closed"):
            continue
        exit_reason = t.get("exit_reason", "")
        if exit_reason not in ("tp_hit", "sl_hit"):
            stats["skipped_manual"] += 1
            continue
        pos_id = t["position_id"]
        cur.execute("SELECT 1 FROM features WHERE position_id = ?", (pos_id,))
        if cur.fetchone():
            stats["skipped_existing"] += 1
            continue
        try:
            entry_time = datetime.fromisoformat(t["entry_time"])
        except (KeyError, ValueError):
            continue
        try:
            feats = extract_features(
                entry_time=entry_time,
                side=t["side"],
                entry_price=float(t["entry_price"]),
                sl=float(t["sl"]) if t.get("sl") else None,
                tp=float(t["tp"]) if t.get("tp") else None,
                symbol=t.get("symbol"),
            )
        except Exception as e:  # noqa: BLE001
            print(f"extract_features failed for pos={pos_id}: {e}")
            stats["skipped_no_features"] += 1
            continue
        if not feats:
            stats["skipped_no_features"] += 1
            continue
        cur.execute(
            "INSERT INTO features(position_id, entry_ts, side, features_json, source, inserted_at)"
            " VALUES(?, ?, ?, ?, 'live', ?)",
            (pos_id, t["entry_time"], t["side"].lower(),
             json.dumps(feats, default=str), datetime.now().isoformat()),
        )
        cur.execute(
            "INSERT INTO outcomes(position_id, won, net_profit, duration_min, exit_reason)"
            " VALUES(?, ?, ?, ?, ?)",
            (pos_id, 1 if exit_reason == "tp_hit" else 0,
             float(t.get("net_profit", 0.0)),
             float(t.get("duration_min", 0.0)), exit_reason),
        )
        stats["ingested"] += 1
    conn.commit()
    return stats


def run_auto_tuner() -> str:
    if not AUTO_TUNER.exists():
        return "auto-tuner missing"
    try:
        proc = subprocess.run(
            [sys.executable, str(AUTO_TUNER)],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        return (proc.stdout or proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return "auto-tuner timeout"
    except Exception as e:  # noqa: BLE001
        return f"auto-tuner error: {e}"


def train_scorer(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    cur.execute("""
        SELECT f.features_json, o.won
        FROM features f JOIN outcomes o ON f.position_id = o.position_id
    """)
    rows = cur.fetchall()
    if len(rows) < MIN_SAMPLES_TO_TRAIN:
        return {"trained": False, "n_samples": len(rows),
                "reason": f"only {len(rows)} samples, need {MIN_SAMPLES_TO_TRAIN}"}
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
    except ImportError as e:
        return {"trained": False, "n_samples": len(rows), "reason": f"missing dep: {e}"}

    X, y = [], []
    for fj, won in rows:
        f = json.loads(fj)
        X.append([float(f.get(c)) if f.get(c) is not None else 0.0 for c in FEATURE_COLUMNS])
        y.append(int(won))
    X = np.array(X)
    y = np.array(y)
    if len(set(y)) < 2:
        return {"trained": False, "n_samples": len(rows),
                "reason": "single-class dataset (need both wins and losses)"}

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=6, random_state=42,
        class_weight="balanced", n_jobs=-1,
    )
    cv_folds = min(5, sum(y), len(y) - sum(y))
    if cv_folds < 2:
        return {"trained": False, "n_samples": len(rows), "reason": "class imbalance too severe for CV"}
    scores = cross_val_score(clf, X, y, cv=cv_folds, scoring="accuracy")
    cv_score = float(scores.mean())
    clf.fit(X, y)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    cur.execute("SELECT COALESCE(MAX(version_id), 0) + 1 FROM model_versions")
    next_id = cur.fetchone()[0]
    model_path = MODELS_DIR / f"scorer_v{next_id}.pkl"
    with model_path.open("wb") as f:
        pickle.dump({"model": clf, "feature_columns": FEATURE_COLUMNS}, f)

    cur.execute(
        "INSERT INTO model_versions(trained_at, n_samples, cv_score, model_path, features_used, notes)"
        " VALUES(?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), len(rows), cv_score, str(model_path),
         json.dumps(FEATURE_COLUMNS), f"RF n_estimators=200 max_depth=6 cv={cv_folds}"),
    )
    conn.commit()
    return {"trained": True, "n_samples": len(rows), "cv_score": cv_score,
            "version": next_id, "model_path": str(model_path)}


def format_report(source_file, stats, train_result, tuner_output) -> str:
    lines = ["Nightly Learner", ""]
    if source_file:
        lines.append(f"Source: {source_file}")
    else:
        lines.append("No trade history available.")
        return "\n".join(lines)
    lines.append(
        f"Trades: considered={stats['considered']} ingested={stats['ingested']} "
        f"skipped_manual={stats['skipped_manual']} existing={stats['skipped_existing']} "
        f"no_features={stats['skipped_no_features']}"
    )
    if train_result.get("trained"):
        lines.append(
            f"Scorer v{train_result['version']} trained "
            f"({train_result['n_samples']} samples, CV={train_result['cv_score'] * 100:.1f}%)"
        )
    else:
        lines.append(f"Scorer: {train_result.get('reason', 'skip')}")
    lines.append("")
    lines.append("Auto-tuner:")
    lines.append(tuner_output[:600] if tuner_output else "(silent)")
    return "\n".join(lines)


def main():
    data, source = load_today_json()
    if data is None:
        print("Nightly Learner\n\nNo trade_history file available.")
        return 0
    conn = sqlite3.connect(str(DB_PATH))
    try:
        init_db(conn)
        stats = ingest_trades(conn, data)
        tuner_out = run_auto_tuner()
        train_result = train_scorer(conn)
        print(format_report(source, stats, train_result, tuner_out))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
