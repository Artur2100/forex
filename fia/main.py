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
    market_agent = MarketAgent()
    technical_agent = TechnicalAgent()
    news_agent = NewsAgent()
    macro_agent = MacroContextAgent()
    correlation_agent = CorrelationAgent()
    risk_agent = RiskAgent()
    chief = ChiefAnalyst()
    state = load_state()

    news = news_agent.analyze()
    macro = macro_agent.analyze(news)
    symbol_results = {}
    decisions = []

    for symbol, ticker in SYMBOLS.items():
        frames, errors = market_agent.fetch(ticker)
        technical = technical_agent.analyze(frames) if frames else {}
        symbol_results[symbol] = technical
        decisions.append(chief.decide(symbol, technical, news, macro, None, risk_agent))
        if errors:
            print(f"{symbol} data errors: {errors}")

    correlation = correlation_agent.analyze(symbol_results)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    new_headlines = [
        f"• {item['title']} ({item['source']})"
        for item in news.get("items", [])[:8]
    ]

    messages = []
    for decision in decisions:
        if decision["status"] != "TECHNICAL_PREALERT":
            continue
        symbol = decision["symbol"]
        key = f"{symbol}|{decision['direction']}|{decision['h1']['bar_time']}"
        if key in state.get("sent", []):
            continue
        state.setdefault("sent", []).append(key)
        levels = decision.get("levels") or {}
        msg = (
            f"⚠️ ТЕХНИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ\n"
            f"{symbol} — {decision['direction']} bias\n"
            f"D1: {decision['d1']['trend']} | H1: {decision['h1']['trend']}\n"
            f"Цена закрытия H1: {fmt_price(decision['h1']['close'])}\n"
        )
        if levels:
            msg += (
                f"Ориентир Entry: {fmt_price(levels['entry_reference'])}\n"
                f"Иллюстративный SL: {fmt_price(levels['stop_loss'])}\n"
                f"Иллюстративный TP: {fmt_price(levels['take_profit'])}\n"
                f"Модельный R:R: 1:{levels['rr_target']:.0f}\n"
            )
        msg += (
            "\nЭто НЕ торговый сигнал и не рекомендация к входу. "
            "Уровни ориентировочные: не учтены спред, комиссии, проскальзывание "
            "и спецификация контракта брокера. Новостной календарь и стратегия не валидированы."
        )
        messages.append(msg)

    digest = (
        f"Forex Intelligence v0.3 — scan {now}\n"
        f"Инструментов: {len(SYMBOLS)}\n"
        f"Технических предупреждений: {len(messages)}\n"
        f"Новостных заголовков получено: {len(news.get('items', []))}\n"
        f"Экономический календарь: НЕ ПОДКЛЮЧЁН / финальные сигналы заблокированы.\n"
        f"Корреляции: {correlation['status']}\n"
    )
    if new_headlines:
        digest += "\nПоследние заголовки RSS:\n" + "\n".join(new_headlines)
    else:
        digest += "\nRSS-источники пока не настроены."
    print(digest)

    send_telegram(digest[:3900])
    for msg in messages:
        send_telegram(msg[:3900])
    save_state(state)

if __name__ == "__main__":
    main()
