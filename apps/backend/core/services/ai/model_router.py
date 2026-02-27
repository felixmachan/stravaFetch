from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteDecision:
    model: str
    allow_escalation: bool = False


def route_model(feature: str, *, low_confidence: bool = False, risk_flags: list[str] | None = None) -> RouteDecision:
    risk_flags = [str(flag).lower() for flag in (risk_flags or [])]
    severe = {"injury", "overtraining", "sudden_load_spike"}
    has_severe_risk = any(flag in severe for flag in risk_flags)
    if low_confidence:
        return RouteDecision(model="gpt-5.2", allow_escalation=True)

    heavy = {"weekly_plan", "general_chat"}
    cheap = {"coach_says", "weekly_summary", "quick_encouragement", "athlete_state_compress"}

    if feature in heavy:
        if has_severe_risk:
            return RouteDecision(model="gpt-5.2", allow_escalation=True)
        return RouteDecision(model="gpt-5-mini")
    if feature in cheap:
        if has_severe_risk:
            return RouteDecision(model="gpt-5.2", allow_escalation=True)
        return RouteDecision(model="gpt-5-nano")
    return RouteDecision(model="gpt-5-mini")
