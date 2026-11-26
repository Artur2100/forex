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

def fmt_price(value):
    if value is None:
        return "n/a"
    return f"{value:.5f}" if abs(value) < 100 else f"{value:.2f}"

def main():
    market_agent, technical_agent = MarketAgent(), TechnicalAgent()
    news_agent, macro_agent = NewsAgent(), MacroContextAgent()
    correlation_agent, risk_agent, chief = CorrelationAgent(), RiskAgent(), ChiefAnalyst()
    state = load_state()
    news = news_agent.analyze()
    macro = macro_agent.analyze(news)
    symbol_results, decisions, diagnostics = {}, [], []

    for symbol, ticker in SYMBOLS.items():
        frames, market_errors = market_agent.fetch(ticker)
        technical, technical_errors = technical_agent.analyze(frames) if frames else ({}, {})
        symbol_results[symbol] = technical
        decision = chief.decide(symbol, technical, news, macro, None, risk_agent)
        decisions.append(decision)
        if market_errors or technical_errors or decision["status"] not in ("TECHNICAL_PREALERT", "NO_SETUP"):
            diagnostics.append(f"• {symbol}: {decision['status']} — {decision.get('reason', '; '.join(market_errors + list(technical_errors.values())) or 'нет подтверждённого сетапа')}")

    correlation = correlation_agent.analyze(symbol_results)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_headlines = [f"• {item['title']} ({item['source']})" for item in news.get("items", [])[:6]]
    messages = []
    for decision in decisions:
        if decision["status"] != "TECHNICAL_PREALERT":
            continue
        symbol = decision["symbol"]
        key = f"{symbol}|{decision['direction']}|{decision['h1']['bar_time']}"
        if key in state.get("sent", []):
            continue
        state.setdefault("sent", []).append(key)
        d1, h1, levels = decision["d1"], decision["h1"], decision["levels"]
        msg = (
            f"⚠️ ТЕХНИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ\n"
            f"{symbol} — {decision['direction']} bias\n"
            f"D1: {d1['trend']} ({d1['ema_slope']}) | H1: {h1['trend']} ({h1['ema_slope']})\n"
            f"Цена закрытия H1: {fmt_price(h1['close'])}\n"
            f"RSI14 H1: {h1['rsi']:.1f} | ADX14 H1: {h1['adx']:.1f}\n"
            f"Свеча H1: {h1['bar_time']} UTC | возраст: {h1['age_hours']:.1f} ч\n"
            f"Ориентир Entry: {fmt_price(levels['entry_reference'])}\n"
            f"Иллюстративный SL: {fmt_price(levels['stop_loss'])}\n"
            f"Иллюстративный TP: {fmt_price(levels['take_profit'])}\n"
            f"Модельный R:R: 1:{levels['rr_target']:.0f}\n\n"
            "Это НЕ торговый сигнал. Котировки — сторонний источник, не поток Альфа-Форекс. "
            "Уровни не учитывают спред, комиссии, проскальзывание и спецификацию контракта. "
            "Экономический календарь и стратегия не валидированы."
        )
        messages.append(msg)

    statuses = {}
    for d in decisions:
        statuses[d["status"]] = statuses.get(d["status"], 0) + 1
    digest = (
        f"Forex Intelligence v0.4 — scan {now}\n"
        f"Инструментов: {len(SYMBOLS)} | Предупреждений: {len(messages)}\n"
        f"Статусы: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())) + "\n"
        f"RSS-заголовков: {len(news.get('items', []))} | Ошибок RSS: {len(news.get('errors', []))}\n"
        f"Экономический календарь: НЕ ПОДКЛЮЧЁН — финальные сигналы заблокированы.\n"
        f"Корреляции: {correlation['status']}\n"
        "Данные: Yahoo Finance, не котировки брокера. Для GC=F используется фьючерс на золото, не спот XAU/USD."
    )
    if diagnostics:
        digest += "\n\nДиагностика (первые 7):\n" + "\n".join(diagnostics[:7])
    if new_headlines:
        digest += "\n\nПоследние RSS-заголовки:\n" + "\n".join(new_headlines)
    print(digest)
    send_telegram(digest[:3900])
    for msg in messages:
        send_telegram(msg[:3900])
    save_state(state)

if __name__ == "__main__":
    main()
