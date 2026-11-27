from datetime import datetime, timezone
from .config import SYMBOLS
from .market_agent import MarketAgent
from .technical_agent import TechnicalAgent
from .news_agent import NewsAgent
from .macro_agent import MacroContextAgent
from .correlation_agent import CorrelationAgent
from .risk_agent import RiskAgent
from .decision_agent import ChiefAnalyst
from .notifier import send_telegram
from .state import load_state, save_state
from .journal import load_journal, save_journal, add_alert, update_outcomes, summary as journal_summary


def fmt_price(value):
    if value is None:
        return "n/a"
    return f"{value:.5f}" if abs(value) < 100 else f"{value:.2f}"


def main():
    market_agent, technical_agent = MarketAgent(), TechnicalAgent()
    news_agent, macro_agent = NewsAgent(), MacroContextAgent()
    correlation_agent, risk_agent, chief = CorrelationAgent(), RiskAgent(), ChiefAnalyst()
    state = load_state()
    journal = load_journal()
    news = news_agent.analyze()
    macro = macro_agent.analyze(news)
    symbol_results, decisions, diagnostics = {}, [], []

    for symbol, ticker in SYMBOLS.items():
        frames, market_errors = market_agent.fetch(ticker)
        technical, technical_errors = technical_agent.analyze(frames) if frames else ({}, {})
        symbol_results[symbol] = {"technical": technical, "frames": frames}
        decision = chief.decide(symbol, technical, news, macro, None, risk_agent)
        decisions.append(decision)
        if market_errors or technical_errors or decision["status"] not in ("TECHNICAL_PREALERT", "NO_SETUP"):
            details = "; ".join(market_errors + list(technical_errors.values()))
            diagnostics.append(f"• {symbol}: {decision['status']} — {decision.get('reason', details or 'нет подтверждённого сетапа')}")
        if symbol == "XAU/USD":
            used = sorted({frame.attrs.get("source_symbol", "unknown") for frame in frames.values()})
            label = "Yahoo spot XAUUSD=X" if used and used == ["XAUUSD=X"] else f"source/proxy: {', '.join(used) or 'unavailable'}"
            diagnostics.append(f"• XAU/USD data source: {label}")

    correlation = correlation_agent.analyze({s: v["technical"] for s, v in symbol_results.items()})
    frames_by_symbol = {s: v["frames"] for s, v in symbol_results.items()}
    journal = update_outcomes(journal, frames_by_symbol)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    messages = []

    for decision in decisions:
        if decision["status"] != "TECHNICAL_PREALERT":
            continue
        symbol, h1 = decision["symbol"], decision["h1"]
        key = f"{symbol}|{decision['direction']}|{h1['bar_time']}"
        if key not in state.get("sent", []):
            state.setdefault("sent", []).append(key)
            levels = decision["levels"]
            side = "BUY" if decision["direction"] == "LONG" else "SELL"
            msg = (
                f"👀 {symbol} · {side} · НАБЛЮДЕНИЕ\n"
                f"Вход: {fmt_price(levels['entry_reference'])}\n"
                f"SL: {fmt_price(levels['stop_loss'])}\n"
                f"TP: {fmt_price(levels['take_profit'])}\n"
                f"R:R 1:{levels['rr_target']:.0f}\n"
                "⚠️ Предварительный сетап, не торговый сигнал. Котировка сторонняя."
            )
            messages.append(msg)
        add_alert(journal, decision)

    save_journal(journal)
    save_state(state)
    stats = journal_summary(journal)
    wr = "н/д" if stats["win_rate_pct"] is None else f"{stats['win_rate_pct']:.1f}%"
    digest = (
        f"Скан {now}\n"
        f"Пар: {len(SYMBOLS)} | новых сетапов: {len(messages)}\n"
        f"Журнал: {stats['total_alerts']} | открыто: {stats['open']} | TP: {stats['wins']} | SL: {stats['losses']} | WR: {wr}"
    )
    if diagnostics:
        digest += "\n\nДиагностика:\n" + "\n".join(diagnostics[:8])
    headlines = news.get("items", [])[:6]
    if headlines:
        digest += "\n\nНовости (приоритетные):\n" + "\n".join(
            f"• [{item['impact']}] {item['title']} ({item['source']})" for item in headlines
        )
    digest += (
        f"\n\nНовостной охват: HIGH {news.get('high_impact_count', 0)}"
        f" | MEDIUM {news.get('medium_impact_count', 0)}"
        f" | ошибок RSS: {len(news.get('errors', []))}"
    )
    digest += "\nRSS не заменяет экономический календарь."
    print(digest)
    send_telegram(digest[:3900])
    for msg in messages:
        send_telegram(msg[:3900])


if __name__ == "__main__":
    main()
