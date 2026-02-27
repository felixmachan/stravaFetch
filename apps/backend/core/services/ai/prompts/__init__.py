from .system_policy import SHARED_SYSTEM_POLICY


def weekly_plan_user_prompt(profile_json: dict, goal_json: dict, athlete_state_json: dict, relevant_workouts_json: list[dict], week_start: str) -> str:
    return (
        f"Create weekly plan for week_start={week_start}. "
        f"profile_json={profile_json} goal_json={goal_json} athlete_state_json={athlete_state_json} "
        f"relevant_workouts_json={relevant_workouts_json}"
    )


def coach_says_user_prompt(workout_json: dict, goal_json: dict, athlete_state_json: dict, training_plan_json: dict) -> str:
    return (
        f"single_workout_json={workout_json} goal_json={goal_json} athlete_state_json={athlete_state_json} "
        f"training_plan_json={training_plan_json}"
    )


def weekly_summary_user_prompt(weekly_stats_json: dict, goal_json: dict, athlete_state_json: dict, training_plan_json: dict) -> str:
    return (
        f"weekly_stats_json={weekly_stats_json} goal_json={goal_json} athlete_state_json={athlete_state_json} "
        f"training_plan_json={training_plan_json}"
    )


def quick_encouragement_user_prompt(weekly_stats_json: dict, goal_json: dict, athlete_state_json: dict, training_plan_json: dict) -> str:
    return (
        f"weekly_stats_json={weekly_stats_json} goal_json={goal_json} athlete_state_json={athlete_state_json} "
        f"training_plan_json={training_plan_json}"
    )


def general_chat_user_prompt(
    message: str,
    profile_json: dict,
    goal_json: dict,
    athlete_state_json: dict,
    relevant_workouts_json: list[dict],
    training_plan_json: dict,
) -> str:
    return (
        f"user_message={message} profile_json={profile_json} goal_json={goal_json} "
        f"athlete_state_json={athlete_state_json} relevant_workouts_json={relevant_workouts_json} training_plan_json={training_plan_json}. "
        "Answer directly and practical. Ask at most one follow-up question only if required."
    )


__all__ = [
    "SHARED_SYSTEM_POLICY",
    "weekly_plan_user_prompt",
    "coach_says_user_prompt",
    "weekly_summary_user_prompt",
    "quick_encouragement_user_prompt",
    "general_chat_user_prompt",
]
