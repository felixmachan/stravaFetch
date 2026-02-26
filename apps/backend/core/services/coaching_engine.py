import datetime as dt
import os
from pydantic import BaseModel, ValidationError
from openai import OpenAI


class NextWorkout(BaseModel):
    sport: str
    title: str
    when: str
    duration_minutes: int
    distance_km: float | None
    intensity: str
    targets: dict
    notes: str


class CoachResponse(BaseModel):
    summary: str
    positives: list[str]
    improvements: list[str]
    effort_label: str
    risk_flags: list[str]
    next_workout: NextWorkout
    plan_adjustment: dict


def deterministic_metrics(activity):
    pace = None
    if activity.distance_m and activity.moving_time_s:
        pace = activity.moving_time_s / (activity.distance_m / 1000)
    intensity = min(200, (activity.avg_hr or 130) * (activity.moving_time_s / 3600))
    return {'avg_pace_sec_per_km': pace, 'intensity_score': intensity}


def generate_coach_json(activity, profile):
    fallback = {
        'summary': 'Solid session completed. Keep consistency and recover well.',
        'positives': ['Completed planned workout'],
        'improvements': ['Keep easy days truly easy'],
        'effort_label': 'moderate',
        'risk_flags': [],
        'next_workout': {
            'sport': activity.type.lower(), 'title': 'Easy recovery session', 'when': str(dt.date.today()),
            'duration_minutes': 40, 'distance_km': None, 'intensity': 'recovery', 'targets': {'pace_min_per_km': None, 'hr_zone': 'Z1'}, 'notes': 'Stay conversational.'
        },
        'plan_adjustment': {'action': 'keep', 'reason': 'No warning signals detected'}
    }
    key = os.getenv('OPENAI_API_KEY', '')
    if not key:
        return fallback
    client = OpenAI(api_key=key)
    prompt = f"Analyze activity metrics and return strict JSON schema only: {fallback}. Activity={activity.raw_payload}, Profile={profile.goals}"
    for i in range(2):
        try:
            r = client.responses.create(model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'), input=prompt)
            text = r.output_text
            parsed = CoachResponse.model_validate_json(text)
            return parsed.model_dump()
        except (ValidationError, Exception):
            prompt = 'Fix JSON only, no markdown.'
    return fallback
