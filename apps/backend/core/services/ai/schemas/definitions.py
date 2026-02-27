from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PlanDay(BaseModel):
    date: str
    type: str
    duration_min: int = Field(ge=0)
    distance_km: float = Field(ge=0)
    intensity_notes: str
    main_set: str
    warmup_cooldown: str
    coach_note: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        allowed = {"rest", "easy", "long", "interval", "tempo", "hills", "cross", "strength"}
        normalized = (value or "").strip().lower()
        return normalized if normalized in allowed else "easy"


class WeeklyPlanOutput(BaseModel):
    week_start_date: str
    plan: list[PlanDay]
    weekly_targets: dict
    risk_notes: list[str] = Field(default_factory=list)


class CoachSaysOutput(BaseModel):
    coach_says: str


class WeeklySummaryOutput(BaseModel):
    headline: str
    highlights: list[str]
    what_to_improve: list[str]
    next_week_focus: list[str]
    risk_flags: list[str] = Field(default_factory=list)


class QuickEncouragementOutput(BaseModel):
    encouragement: str


WEEKLY_PLAN_SCHEMA = {
    "name": "weekly_plan",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["week_start_date", "plan", "weekly_targets", "risk_notes"],
        "properties": {
            "week_start_date": {"type": "string"},
            "plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "date",
                        "type",
                        "duration_min",
                        "distance_km",
                        "intensity_notes",
                        "main_set",
                        "warmup_cooldown",
                        "coach_note",
                    ],
                    "properties": {
                        "date": {"type": "string"},
                        "type": {"type": "string"},
                        "duration_min": {"type": "integer", "minimum": 0},
                        "distance_km": {"type": "number", "minimum": 0},
                        "intensity_notes": {"type": "string"},
                        "main_set": {"type": "string"},
                        "warmup_cooldown": {"type": "string"},
                        "coach_note": {"type": "string"},
                    },
                },
            },
            "weekly_targets": {
                "type": "object",
                "additionalProperties": False,
                "required": ["total_distance_km", "total_duration_min", "hard_sessions", "focus"],
                "properties": {
                    "total_distance_km": {"type": "number", "minimum": 0},
                    "total_duration_min": {"type": "integer", "minimum": 0},
                    "hard_sessions": {"type": "integer", "minimum": 0},
                    "focus": {"type": "string"},
                },
            },
            "risk_notes": {"type": "array", "items": {"type": "string"}},
        },
    },
}


WEEKLY_SUMMARY_SCHEMA = {
    "name": "weekly_summary",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["headline", "highlights", "what_to_improve", "next_week_focus", "risk_flags"],
        "properties": {
            "headline": {"type": "string"},
            "highlights": {"type": "array", "items": {"type": "string"}},
            "what_to_improve": {"type": "array", "items": {"type": "string"}},
            "next_week_focus": {"type": "array", "items": {"type": "string"}},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
        },
    },
}


COACH_SAYS_SCHEMA = {
    "name": "coach_says",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["coach_says"],
        "properties": {"coach_says": {"type": "string"}},
    },
}


QUICK_ENCOURAGEMENT_SCHEMA = {
    "name": "quick_encouragement",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["encouragement"],
        "properties": {"encouragement": {"type": "string"}},
    },
}
