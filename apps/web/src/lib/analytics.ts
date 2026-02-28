export type Activity = {
  id: number;
  name: string;
  type: string;
  sport_type?: string;
  start_date: string;
  start_date_local?: string | null;
  timezone_name?: string;
  distance_m: number;
  moving_time_s: number;
  elapsed_time_s?: number;
  average_speed_mps?: number;
  max_speed_mps?: number;
  average_cadence?: number | null;
  average_watts?: number | null;
  weighted_average_watts?: number | null;
  max_watts?: number | null;
  kilojoules?: number | null;
  avg_hr?: number | null;
  max_hr?: number | null;
  total_elevation_gain_m?: number;
  average_temp?: number | null;
  elev_high?: number | null;
  elev_low?: number | null;
  suffer_score?: number | null;
  achievement_count?: number;
  kudos_count?: number;
  comment_count?: number;
  device_name?: string;
  trainer?: boolean;
  commute?: boolean;
  manual?: boolean;
  fully_synced?: boolean;
  sync_error?: string;
  map_summary_polyline?: string | null;
  raw_payload?: Record<string, any>;
};

const DAY_MS = 24 * 60 * 60 * 1000;
export type WeekRange = { start: Date; end: Date; days: Date[] };

export function km(distanceM = 0) {
  return distanceM / 1000;
}

export function pacePerKm(distanceM = 0, movingTimeS = 0) {
  if (!distanceM || !movingTimeS) return 0;
  return movingTimeS / (distanceM / 1000);
}

export function formatDuration(seconds = 0) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function formatPace(secPerKm = 0) {
  if (!secPerKm) return 'n/a';
  const m = Math.floor(secPerKm / 60);
  const s = Math.round(secPerKm % 60)
    .toString()
    .padStart(2, '0');
  return `${m}:${s} /km`;
}

export function groupByWeek(activities: Activity[], days = 28) {
  const now = Date.now();
  const filtered = activities.filter((a) => now - new Date(a.start_date).getTime() <= days * DAY_MS);
  const byWeek: Record<string, { distance: number; time: number; load: number; run: number; ride: number; swim: number }> = {};

  for (const a of filtered) {
    const dt = new Date(a.start_date);
    const week = `${dt.getFullYear()}-W${Math.ceil((dt.getDate() + 6 - dt.getDay()) / 7)}`;
    if (!byWeek[week]) {
      byWeek[week] = { distance: 0, time: 0, load: 0, run: 0, ride: 0, swim: 0 };
    }
    const intensity = a.suffer_score ?? Math.min(100, (a.avg_hr || 140) / 2);
    byWeek[week].distance += km(a.distance_m);
    byWeek[week].time += a.moving_time_s / 60;
    byWeek[week].load += (a.moving_time_s / 60) * (intensity / 100);
    const kind = a.type.toLowerCase();
    if (kind.includes('run')) byWeek[week].run += km(a.distance_m);
    if (kind.includes('ride')) byWeek[week].ride += km(a.distance_m);
    if (kind.includes('swim')) byWeek[week].swim += km(a.distance_m);
  }

  return Object.entries(byWeek)
    .map(([week, value]) => ({ week, ...value }))
    .sort((a, b) => a.week.localeCompare(b.week));
}

export function startOfWeekMonday(date: Date) {
  const d = new Date(date);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + diff);
  return d;
}

export function getWeekRange(date = new Date()): WeekRange {
  const start = startOfWeekMonday(date);
  const days = Array.from({ length: 7 }).map((_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  end.setHours(23, 59, 59, 999);
  return { start, end, days };
}

function dayKey(date: Date) {
  return date.toISOString().slice(0, 10);
}

export function groupActivitiesByDay(activities: Activity[], range: WeekRange) {
  const map: Record<string, Activity[]> = {};
  for (const d of range.days) map[dayKey(d)] = [];
  for (const a of activities) {
    const dt = new Date(a.start_date);
    if (dt >= range.start && dt <= range.end) {
      const key = dayKey(dt);
      if (!map[key]) map[key] = [];
      map[key].push(a);
    }
  }
  return map;
}

export function weeklyDistanceBySport(activities: Activity[], range: WeekRange) {
  const out = { total: 0, run: 0, swim: 0, ride: 0 };
  for (const a of activities) {
    const dt = new Date(a.start_date);
    if (dt < range.start || dt > range.end) continue;
    const distKm = km(a.distance_m);
    out.total += distKm;
    const kind = (a.type || "").toLowerCase();
    if (kind.includes("run")) out.run += distKm;
    if (kind.includes("swim")) out.swim += distKm;
    if (kind.includes("ride")) out.ride += distKm;
  }
  return out;
}

export function weeklyActivityCountsBySport(activities: Activity[], range: WeekRange) {
  const out = { total: 0, run: 0, swim: 0, ride: 0 };
  for (const a of activities) {
    const dt = new Date(a.start_date);
    if (dt < range.start || dt > range.end) continue;
    out.total += 1;
    const kind = (a.type || "").toLowerCase();
    if (kind.includes("run")) out.run += 1;
    if (kind.includes("swim")) out.swim += 1;
    if (kind.includes("ride")) out.ride += 1;
  }
  return out;
}

export function activityStreak(activities: Activity[]) {
  const dates = new Set(activities.map((a) => new Date(a.start_date).toISOString().slice(0, 10)));
  let streak = 0;
  const current = new Date();

  for (let i = 0; i < 60; i += 1) {
    const d = new Date(current.getTime() - i * DAY_MS).toISOString().slice(0, 10);
    if (dates.has(d)) streak += 1;
    else if (streak > 0) break;
  }
  return streak;
}

export function buildInsights(activities: Activity[]) {
  const weeks = groupByWeek(activities, 56);
  const current = weeks[weeks.length - 1];
  const previous = weeks[weeks.length - 2];

  const jump = current && previous && previous.distance > 0 ? ((current.distance - previous.distance) / previous.distance) * 100 : 0;
  const sevenDays = activities.filter((a) => Date.now() - new Date(a.start_date).getTime() <= 7 * DAY_MS);

  return {
    rampWarning: jump > 15,
    jump,
    streak: activityStreak(activities),
    weeklySessions: sevenDays.length,
    coachTone:
      sevenDays.length >= 4
        ? 'Your consistency this week is strong. Keep the quality high and respect recovery days.'
        : 'Volume is light this week. A short aerobic session today will rebuild rhythm.',
    nextWorkout:
      jump > 15
        ? '40 min easy run + 4 strides to absorb the recent load spike.'
        : '50 min steady aerobic run with 6 x 20s pickups for economy.',
    readiness:
      jump > 15 ? 58 : 76,
  };
}
