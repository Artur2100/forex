class MacroContextAgent:
    name = "Macro Context Agent"

    def analyze(self, news_result):
        return {
            "status": "CONTEXT_ONLY",
            "headline_count": len(news_result.get("items", [])),
            "calendar_validated": False,
            "conclusion": "Macro direction is not scored until reliable event data and currency mapping are validated."
        }
