import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

JOURNAL_PATH = Path("journal.csv")
FIELDS = [
    "id", "created_utc", "symbol", "direction", "source", "entry", "sl", "tp",
    "status", "outcome_r", "resolved_utc", "bars_to_resolution", "notes"
]

def _dt(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)

def load_journal():
    if not JOURNAL_PATH.exists():
        return []
    with JOURNAL_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def save_journal(rows):
    with JOURNAL_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

def add_alert(rows, decision, source="Yahoo Finance"):
    h1, levels = decision["h1"], decision["levels"]
    key = f"{decision['symbol']}|{decision['direction']}|{h1['bar_time']}"
    if any(row["id"] == key for row in rows):
        return False
    rows.append({
        "id": key,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": decision["symbol"],
        "direction": decision["direction"],
        "source": source,
        "entry": f"{levels['entry_reference']:.10g}",
        "sl": f"{levels['stop_loss']:.10g}",
        "tp": f"{levels['take_profit']:.10g}",
        "status": "OPEN",
        "outcome_r": "",
        "resolved_utc": "",
        "bars_to_resolution": "",
        "notes": "Hypothetical alert; assumes entry at completed H1 close; not a real executed trade."
    })
    return True

def update_outcomes(rows, frames_by_symbol, max_days=7):
    now = datetime.now(timezone.utc)
    for row in rows:
        if row["status"] != "OPEN":
            continue
        frame = frames_by_symbol.get(row["symbol"], {}).get("H1")
        if frame is None or frame.empty:
            continue
        entry_time = _dt(row["id"].rsplit("|", 1)[-1])
        entry = float(row["entry"])
        sl, tp = float(row["sl"]), float(row["tp"])
        direction = row["direction"]
        bars = frame.copy()
        if bars.index.tz is None:
            bars.index = bars.index.tz_localize("UTC")
        else:
            bars.index = bars.index.tz_convert("UTC")
        bars = bars[bars.index > entry_time]
        for stamp, candle in bars.iterrows():
            high, low = float(candle["high"]), float(candle["low"])
            if direction == "LONG":
                sl_hit, tp_hit = low <= sl, high >= tp
            else:
                sl_hit, tp_hit = high >= sl, low <= tp
            if sl_hit and tp_hit:
                row["status"] = "AMBIGUOUS_SAME_CANDLE"
                row["outcome_r"] = ""
            elif tp_hit:
                row["status"] = "TP_HIT"
                row["outcome_r"] = "3.0"
            elif sl_hit:
                row["status"] = "SL_HIT"
                row["outcome_r"] = "-1.0"
            else:
                continue
            row["resolved_utc"] = stamp.to_pydatetime().isoformat()
            row["bars_to_resolution"] = str(int((bars.index <= stamp).sum()))
            break
        if row["status"] == "OPEN" and now - entry_time > timedelta(days=max_days):
            row["status"] = "EXPIRED_7D"
            row["resolved_utc"] = now.isoformat()
            row["notes"] += " No TP/SL touch detected in available data within 7 days."
    return rows

def summary(rows):
    closed = [r for r in rows if r["status"] in ("TP_HIT", "SL_HIT")]
    wins = sum(r["status"] == "TP_HIT" for r in closed)
    losses = sum(r["status"] == "SL_HIT" for r in closed)
    decided = wins + losses
    total_r = sum(float(r["outcome_r"]) for r in closed)
    return {
        "total_alerts": len(rows),
        "open": sum(r["status"] == "OPEN" for r in rows),
        "wins": wins,
        "losses": losses,
        "ambiguous": sum(r["status"] == "AMBIGUOUS_SAME_CANDLE" for r in rows),
        "expired": sum(r["status"] == "EXPIRED_7D" for r in rows),
        "win_rate_pct": (wins / decided * 100) if decided else None,
        "net_r": total_r,
        "closed": decided
    }
