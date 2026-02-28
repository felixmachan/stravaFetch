import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Bike, Calendar, PersonStanding, Target, Waves } from '../components/ui/icons';
import { api } from '../lib/api';
import { Activity, getWeekRange, km, weeklyActivityCountsBySport } from '../lib/analytics';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Progress } from '../components/ui/progress';
import { Button } from '../components/ui/button';

type GoalPayload = {
  type: 'race' | 'time_trial' | 'annual_km';
  target_distance_km?: number | null;
  target_time_min?: number | null;
  race_distance_km?: number | null;
  has_time_goal?: boolean;
  event_name?: string;
  event_date?: string;
  annual_km_goal?: number | null;
  weekly_activity_goal_total?: number;
  weekly_activity_goal_run?: number;
  weekly_activity_goal_swim?: number;
  weekly_activity_goal_ride?: number;
  training_days?: string[];
  weekly_plan_generation_day?: 'sat' | 'sun' | string;
  weekly_plan_generation_hour?: number;
  notes?: string;
};

type PlannedSession = {
  date: string;
  sport: string;
  duration_min?: number;
  distance_km?: number;
  hr_zone?: string;
  title?: string;
  workout_type?: string;
  coach_notes?: string;
  status?: 'planned' | 'done' | 'partial_done' | 'missed';
};

type WeekPlan = {
  week_start?: string;
  week_end?: string;
  days?: PlannedSession[];
};

const DAY_LABELS: Record<string, string> = {
  mon: 'Monday',
  tue: 'Tuesday',
  wed: 'Wednesday',
  thu: 'Thursday',
  fri: 'Friday',
  sat: 'Saturday',
  sun: 'Sunday',
};
const TRAINING_DAYS = [
  { key: 'mon', label: 'Mon' },
  { key: 'tue', label: 'Tue' },
  { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' },
  { key: 'fri', label: 'Fri' },
  { key: 'sat', label: 'Sat' },
  { key: 'sun', label: 'Sun' },
] as const;

function formatDays(days: string[]) {
  if (!days.length) return 'Not set';
  return days.map((d) => DAY_LABELS[d] || d).join(', ');
}

function typeLabel(goal: GoalPayload) {
  if (goal.type === 'race') return 'Race goal';
  if (goal.type === 'time_trial') return 'Distance + time goal';
  return 'Annual distance goal';
}

function sportIcon(sport = '') {
  const s = sport.toLowerCase();
  if (s.includes('swim')) return <Waves className='h-4 w-4 text-cyan-300' />;
  if (s.includes('ride') || s.includes('bike') || s.includes('cycle')) return <Bike className='h-4 w-4 text-sky-300' />;
  return <PersonStanding className='h-4 w-4 text-rose-300' />;
}

export function PlanPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: activities } = useQuery({
    queryKey: ['activities'],
    queryFn: async () => (await api.get('/activities')).data as Activity[],
  });
  const { data: profileData } = useQuery({
    queryKey: ['profile'],
    queryFn: async () => (await api.get('/profile')).data as any,
  });
  const { data: goalData } = useQuery({
    queryKey: ['goal'],
    queryFn: async () => (await api.get('/goal')).data as GoalPayload,
  });
  const { data: weekPlan } = useQuery<WeekPlan>({
    queryKey: ['plan-current-week'],
    queryFn: async () => (await api.get('/plan/current-week')).data,
  });

  const [goal, setGoal] = useState<GoalPayload>({ type: 'race' });
  const [editingGoal, setEditingGoal] = useState(false);
  const [editingWeekly, setEditingWeekly] = useState(false);
  const [nowTick, setNowTick] = useState(Date.now());

  function toggleWeeklyTrainingDay(day: string) {
    setGoal((prev) => {
      const existing = (prev.training_days || []).map((d) => String(d).toLowerCase().slice(0, 3));
      const isSelected = existing.includes(day);
      const next = isSelected ? existing.filter((d) => d !== day) : [...existing, day];
      return {
        ...prev,
        training_days: next,
        weekly_activity_goal_total: next.length,
      };
    });
  }

  useEffect(() => {
    if (goalData) setGoal(goalData);
  }, [goalData]);
  useEffect(() => {
    if (!profileData) return;
    setGoal((prev) => {
      if (Array.isArray(prev.training_days) && prev.training_days.length > 0) return prev;
      const fromProfile = ((profileData?.schedule || {}).training_days || []) as string[];
      if (!fromProfile.length) return prev;
      return {
        ...prev,
        training_days: fromProfile.map((d) => String(d).toLowerCase().slice(0, 3)),
        weekly_activity_goal_total: Number(prev.weekly_activity_goal_total || fromProfile.length),
      };
    });
  }, [profileData]);
  useEffect(() => {
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const week = useMemo(() => getWeekRange(new Date()), []);
  const weeklyCounts = useMemo(() => weeklyActivityCountsBySport(activities || [], week), [activities, week]);
  const splitSum = Number(goal.weekly_activity_goal_run || 0) + Number(goal.weekly_activity_goal_swim || 0) + Number(goal.weekly_activity_goal_ride || 0);
  const splitValid = splitSum <= Number(goal.weekly_activity_goal_total || 0);

  const saveGoalDefinition = useMutation({
    mutationFn: async () =>
      api.patch('/goal', {
        type: goal.type,
        event_name: goal.event_name,
        event_date: goal.event_date,
        race_distance_km: goal.race_distance_km,
        has_time_goal: goal.has_time_goal,
        target_time_min: goal.target_time_min,
        target_distance_km: goal.target_distance_km,
        annual_km_goal: goal.annual_km_goal,
        notes: goal.notes,
      }),
    onSuccess: async () => {
      qc.invalidateQueries({ queryKey: ['goal'] });
      setEditingGoal(false);
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Goal saved', message: 'Goal definition updated.' } }));
    },
  });

  const saveWeeklyGoal = useMutation({
    mutationFn: async () =>
      api.patch('/goal', {
        weekly_activity_goal_total: Number(goal.weekly_activity_goal_total || 0),
        weekly_activity_goal_run: Number(goal.weekly_activity_goal_run || 0),
        weekly_activity_goal_swim: Number(goal.weekly_activity_goal_swim || 0),
        weekly_activity_goal_ride: Number(goal.weekly_activity_goal_ride || 0),
        training_days: goal.training_days || [],
        weekly_plan_generation_day: (goal.weekly_plan_generation_day || 'sun').toString().slice(0, 3),
        weekly_plan_generation_hour: Number(goal.weekly_plan_generation_hour ?? 2),
      }),
    onSuccess: async () => {
      qc.invalidateQueries({ queryKey: ['goal'] });
      setEditingWeekly(false);
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Weekly goal saved', message: 'Weekly targets updated.' } }));
    },
  });

  const regenerateWeekPlan = useMutation({
    mutationFn: async () => (await api.post('/plan/generate-week', { force: true })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plan-current-week'] });
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Weekly plan updated', message: 'AI generated a fresh weekly plan.' } }));
    },
  });

  const distance28d = useMemo(
    () =>
      (activities || [])
        .filter((a) => Date.now() - new Date(a.start_date).getTime() <= 28 * 24 * 60 * 60 * 1000)
        .reduce((sum, a) => sum + km(a.distance_m), 0),
    [activities]
  );

  const weeksToGoal = useMemo(() => {
    if (!goal?.event_date) return null;
    const diff = new Date(goal.event_date).getTime() - Date.now();
    return Math.max(0, Math.ceil(diff / (7 * 24 * 60 * 60 * 1000)));
  }, [goal?.event_date]);

  const progressScore = Math.max(8, Math.min(95, Math.round(weeklyCounts.total * 14 + distance28d / 4)));
  const trainingDays = (goal.training_days || ((profileData?.schedule || {}).training_days || [])) as string[];
  const nextAutoGeneration = useMemo(() => {
    const day = String(goal.weekly_plan_generation_day || 'sun').slice(0, 3).toLowerCase();
    const hour = Math.max(0, Math.min(23, Number(goal.weekly_plan_generation_hour ?? 2)));
    const now = new Date(nowTick);
    const map: Record<string, number> = { mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6, sun: 0 };
    const targetDow = map[day] ?? 0;
    const candidate = new Date(now);
    candidate.setMinutes(0, 0, 0);
    candidate.setHours(hour);
    const diff = (targetDow - now.getDay() + 7) % 7;
    candidate.setDate(now.getDate() + diff);
    if (candidate.getTime() <= now.getTime()) candidate.setDate(candidate.getDate() + 7);
    return candidate;
  }, [goal.weekly_plan_generation_day, goal.weekly_plan_generation_hour, nowTick]);
  const autoGenerationCountdown = useMemo(() => {
    const deltaMs = Math.max(0, nextAutoGeneration.getTime() - nowTick);
    const sec = Math.floor(deltaMs / 1000);
    const days = Math.floor(sec / 86400);
    const hours = Math.floor((sec % 86400) / 3600);
    const mins = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${days}d ${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }, [nextAutoGeneration, nowTick]);
  const goalSummaryCards = useMemo(() => {
    const cards: Array<{ label: string; value: string }> = [{ label: 'Goal type', value: typeLabel(goal) }];
    if (goal.type === 'race') {
      if (goal.event_name) cards.push({ label: 'Event', value: goal.event_name });
      if (goal.event_date) cards.push({ label: 'Date', value: goal.event_date });
      if (goal.race_distance_km) cards.push({ label: 'Race distance', value: `${goal.race_distance_km} km` });
      if (goal.has_time_goal && goal.target_time_min) cards.push({ label: 'Time goal', value: `${goal.target_time_min} min` });
    } else if (goal.type === 'time_trial') {
      if (goal.target_distance_km) cards.push({ label: 'Distance', value: `${goal.target_distance_km} km` });
      if (goal.target_time_min) cards.push({ label: 'Target time', value: `${goal.target_time_min} min` });
    } else if (goal.type === 'annual_km' && goal.annual_km_goal) {
      cards.push({ label: 'Annual target', value: `${goal.annual_km_goal} km` });
    }
    if (goal.notes) cards.push({ label: 'Notes', value: goal.notes });
    return cards;
  }, [goal]);
  const primaryGoalCards = useMemo(() => goalSummaryCards.filter((c) => c.label !== 'Notes'), [goalSummaryCards]);
  const goalNotesCard = useMemo(() => goalSummaryCards.find((c) => c.label === 'Notes'), [goalSummaryCards]);

  const upcoming = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return ((weekPlan?.days || []) as PlannedSession[])
      .filter((s) => (s.status || 'planned') === 'planned' && String(s.date || '') >= today)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [weekPlan?.days]);

  return (
    <div className='space-y-4'>
      <Card className='border-cyan-400/25 bg-gradient-to-r from-red-500/10 via-slate-900/80 to-cyan-500/10 p-6 shadow-[0_0_0_1px_rgba(34,211,238,0.08),0_18px_50px_-30px_rgba(6,182,212,0.65)]'>
        <div className='flex items-center justify-between'>
          <div>
            <p className='flex items-center gap-2 text-2xl font-semibold'><Target className='h-5 w-5 text-cyan-300' />Goal Definition</p>
            <p className='mt-1 text-sm text-muted-foreground'>Goal data is read-only by default. Use edit when needed.</p>
          </div>
          <Button variant={editingGoal ? 'outline' : 'default'} onClick={() => setEditingGoal((v) => !v)}>
            {editingGoal ? 'Cancel edit' : 'Edit goal'}
          </Button>
        </div>

        {!editingGoal ? (
          <>
            <div className='mt-4 flex items-stretch gap-3 overflow-x-auto pb-1'>
              {primaryGoalCards.map((card) => (
                <div
                  key={card.label}
                  className='min-w-[220px] rounded-xl border border-cyan-400/25 bg-slate-950/45 px-4 py-3 backdrop-blur-sm'
                >
                  <p className='text-xs uppercase tracking-wide text-cyan-100/70'>{card.label}</p>
                  <p className='text-2xl font-semibold text-slate-100'>{card.value}</p>
                </div>
              ))}
            </div>
            {goalNotesCard ? (
              <div
                className='mt-3 rounded-xl border border-cyan-300/20 bg-slate-950/35 p-3'
              >
                <p className='text-xs uppercase tracking-wide text-cyan-100/70'>Notes</p>
                <p className='text-sm text-slate-200'>{goalNotesCard.value}</p>
              </div>
            ) : null}
          </>
        ) : (
          <div className='mt-4 space-y-4'>
            <div className='grid gap-4 md:grid-cols-2'>
              <label className='space-y-1'>
                <span className='text-sm text-muted-foreground'>Goal type</span>
                <select
                  className='h-10 w-full rounded-xl border border-border bg-background px-3 text-sm'
                  value={goal.type || 'race'}
                  onChange={(e) => setGoal((p) => ({ ...p, type: e.target.value as GoalPayload['type'] }))}
                >
                  <option value='race'>Race goal</option>
                  <option value='time_trial'>Distance + time goal</option>
                  <option value='annual_km'>Annual distance goal</option>
                </select>
              </label>

              {goal.type === 'race' && (
                <>
                  <label className='space-y-1'>
                    <span className='text-sm text-muted-foreground'>Event name</span>
                    <Input value={goal.event_name || ''} onChange={(e) => setGoal((p) => ({ ...p, event_name: e.target.value }))} placeholder='Budapest Half Marathon' />
                  </label>
                  <label className='space-y-1'>
                    <span className='text-sm text-muted-foreground'><Calendar className='mr-1 inline h-4 w-4' />Event date</span>
                    <Input type='date' value={goal.event_date || ''} onChange={(e) => setGoal((p) => ({ ...p, event_date: e.target.value }))} />
                  </label>
                  <label className='space-y-1'>
                    <span className='text-sm text-muted-foreground'>Race distance (km)</span>
                    <Input type='number' step='0.1' value={goal.race_distance_km ?? ''} onChange={(e) => setGoal((p) => ({ ...p, race_distance_km: Number(e.target.value || 0) || null }))} placeholder='21.1' />
                  </label>
                  <label className='space-y-2'>
                    <span className='text-sm text-muted-foreground'>Time goal</span>
                    <label className='flex items-center gap-2 text-sm'>
                      <input type='checkbox' checked={Boolean(goal.has_time_goal)} onChange={(e) => setGoal((p) => ({ ...p, has_time_goal: e.target.checked, target_time_min: e.target.checked ? p.target_time_min ?? null : null }))} />
                      I have a time goal as well
                    </label>
                  </label>
                  {goal.has_time_goal && (
                    <label className='space-y-1'>
                      <span className='text-sm text-muted-foreground'>Target time (min)</span>
                      <Input type='number' value={goal.target_time_min ?? ''} onChange={(e) => setGoal((p) => ({ ...p, target_time_min: Number(e.target.value || 0) || null }))} placeholder='110' />
                    </label>
                  )}
                </>
              )}

              {goal.type === 'time_trial' && (
                <>
                  <label className='space-y-1'>
                    <span className='text-sm text-muted-foreground'>Distance (km)</span>
                    <Input type='number' step='0.1' value={goal.target_distance_km ?? ''} onChange={(e) => setGoal((p) => ({ ...p, target_distance_km: Number(e.target.value || 0) || null }))} placeholder='5' />
                  </label>
                  <label className='space-y-1'>
                    <span className='text-sm text-muted-foreground'>Target time (min)</span>
                    <Input type='number' value={goal.target_time_min ?? ''} onChange={(e) => setGoal((p) => ({ ...p, target_time_min: Number(e.target.value || 0) || null }))} placeholder='20' />
                  </label>
                </>
              )}

              {goal.type === 'annual_km' && (
                <label className='space-y-1'>
                  <span className='text-sm text-muted-foreground'>Annual km goal</span>
                  <Input type='number' value={goal.annual_km_goal ?? ''} onChange={(e) => setGoal((p) => ({ ...p, annual_km_goal: Number(e.target.value || 0) || null }))} placeholder='1800' />
                </label>
              )}
            </div>
            <label className='block space-y-1'>
              <span className='text-sm text-muted-foreground'>Goal notes and constraints</span>
              <textarea className='min-h-24 w-full rounded-xl border border-border bg-background p-3 text-sm' value={goal.notes || ''} onChange={(e) => setGoal((p) => ({ ...p, notes: e.target.value }))} />
            </label>
            <div className='flex items-center gap-2'>
              <Button onClick={() => saveGoalDefinition.mutate()} disabled={saveGoalDefinition.isPending}>{saveGoalDefinition.isPending ? 'Saving...' : 'Save goal'}</Button>
            </div>
          </div>
        )}

      </Card>

      <Card className='p-6'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <div>
            <p className='text-xl font-semibold'>Weekly Goal</p>
            <p className='text-sm text-muted-foreground'>Session target and sport split.</p>
          </div>
          <div className='flex items-center gap-2'>
            <Button variant='outline' onClick={() => regenerateWeekPlan.mutate()} disabled={regenerateWeekPlan.isPending}>
              {regenerateWeekPlan.isPending ? 'Generating week...' : 'Regenerate week plan'}
            </Button>
            <Button variant={editingWeekly ? 'outline' : 'default'} onClick={() => setEditingWeekly((v) => !v)}>{editingWeekly ? 'Cancel edit' : 'Edit weekly goal'}</Button>
          </div>
        </div>

        {!editingWeekly ? (
          <div className='mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-5'>
            <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Total sessions/week</p><p className='text-2xl font-semibold'>{goal.weekly_activity_goal_total || 0}</p></div>
            <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Run</p><p className='text-2xl font-semibold'>{goal.weekly_activity_goal_run || 0}</p></div>
            <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Swim</p><p className='text-2xl font-semibold'>{goal.weekly_activity_goal_swim || 0}</p></div>
            <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Ride</p><p className='text-2xl font-semibold'>{goal.weekly_activity_goal_ride || 0}</p></div>
            <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Progress this week</p><p className='text-2xl font-semibold'>{weeklyCounts.total}/{goal.weekly_activity_goal_total || 0}</p></div>
            <div className='rounded-xl border border-border p-3 md:col-span-2 lg:col-span-5'>
              <p className='text-xs text-muted-foreground'>Training days</p>
              <p className='text-base font-semibold'>{formatDays(trainingDays)}</p>
            </div>
          </div>
        ) : (
          <>
            <div className='mt-4 grid gap-4 md:grid-cols-4'>
              <label className='space-y-1'>
                <span className='text-sm text-muted-foreground'>Total sessions / week</span>
                <Input type='number' value={goal.weekly_activity_goal_total ?? 0} onChange={(e) => setGoal((p) => ({ ...p, weekly_activity_goal_total: Number(e.target.value || 0) }))} />
              </label>
              <label className='space-y-1'>
                <span className='text-sm text-muted-foreground'>Run</span>
                <Input type='number' value={goal.weekly_activity_goal_run ?? 0} onChange={(e) => setGoal((p) => ({ ...p, weekly_activity_goal_run: Number(e.target.value || 0) }))} />
              </label>
              <label className='space-y-1'>
                <span className='text-sm text-muted-foreground'>Swim</span>
                <Input type='number' value={goal.weekly_activity_goal_swim ?? 0} onChange={(e) => setGoal((p) => ({ ...p, weekly_activity_goal_swim: Number(e.target.value || 0) }))} />
              </label>
              <label className='space-y-1'>
                <span className='text-sm text-muted-foreground'>Ride</span>
                <Input type='number' value={goal.weekly_activity_goal_ride ?? 0} onChange={(e) => setGoal((p) => ({ ...p, weekly_activity_goal_ride: Number(e.target.value || 0) }))} />
              </label>
            </div>
            <div className='mt-4 space-y-2'>
              <p className='text-sm text-muted-foreground'>Training days (used by AI weekly planning)</p>
              <div className='grid grid-cols-4 gap-2 sm:grid-cols-7'>
                {TRAINING_DAYS.map((d) => {
                  const selected = (goal.training_days || []).includes(d.key);
                  return (
                    <button
                      key={d.key}
                      type='button'
                      onClick={() => toggleWeeklyTrainingDay(d.key)}
                      className={`rounded-xl border px-3 py-2 text-sm transition ${
                        selected
                          ? 'border-emerald-400/60 bg-emerald-500/15 text-emerald-200'
                          : 'border-border bg-muted/25 text-muted-foreground hover:border-cyan-400/40'
                      }`}
                    >
                      {d.label}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className='mt-4 grid gap-4 md:grid-cols-2'>
              <label className='space-y-1'>
                <span className='text-sm text-muted-foreground'>Auto-generate next week on</span>
                <select
                  className='h-10 w-full rounded-xl border border-border bg-background px-3 text-sm'
                  value={String(goal.weekly_plan_generation_day || 'sun').slice(0, 3)}
                  onChange={(e) => setGoal((p) => ({ ...p, weekly_plan_generation_day: e.target.value as 'sat' | 'sun' }))}
                >
                  <option value='sat'>Saturday</option>
                  <option value='sun'>Sunday</option>
                </select>
              </label>
              <label className='space-y-1'>
                <span className='text-sm text-muted-foreground'>Auto-generate hour (0-23)</span>
                <Input
                  type='number'
                  min={0}
                  max={23}
                  value={goal.weekly_plan_generation_hour ?? 2}
                  onChange={(e) => setGoal((p) => ({ ...p, weekly_plan_generation_hour: Math.max(0, Math.min(23, Number(e.target.value || 0))) }))}
                />
              </label>
            </div>
            <div className='mt-3 flex items-center gap-2'>
              <div className={`rounded-xl border px-3 py-1.5 text-sm ${splitValid ? 'border-emerald-400/40 text-emerald-300' : 'border-rose-400/40 text-rose-300'}`}>
                {splitValid ? 'Sport split is valid' : 'Run + Swim + Ride cannot exceed total'}
              </div>
              <Button onClick={() => saveWeeklyGoal.mutate()} disabled={!splitValid || saveWeeklyGoal.isPending}>{saveWeeklyGoal.isPending ? 'Saving...' : 'Save weekly goal'}</Button>
            </div>
          </>
        )}
        <div className='mt-3 rounded-xl border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100'>
          Next auto-generation: {nextAutoGeneration.toLocaleString()} ({autoGenerationCountdown})
        </div>
      </Card>

      <Card className='p-6'>
        <p className='text-lg font-semibold'>Readiness and Progress</p>
        <div className='mt-4 grid gap-4 lg:grid-cols-[1.2fr_1fr]'>
          <div>
            <p className='text-sm text-muted-foreground'>Plan completion estimate</p>
            <p className='mb-2 text-3xl font-semibold'>{progressScore}%</p>
            <Progress value={progressScore} />
            <p className='mt-3 text-sm text-muted-foreground'>Training days: {formatDays(trainingDays)}</p>
          </div>
          <div className='grid gap-2 sm:grid-cols-2'>
            <div className='rounded-xl border border-border p-3'>
              <p className='text-xs text-muted-foreground'>Weeks to goal</p>
              <p className='text-lg font-semibold'>{weeksToGoal != null ? weeksToGoal : 'n/a'}</p>
            </div>
            <div className='rounded-xl border border-border p-3'>
              <p className='text-xs text-muted-foreground'>Sessions (7d)</p>
              <p className='text-lg font-semibold'>{weeklyCounts.total}</p>
            </div>
            <div className='rounded-xl border border-border p-3'>
              <p className='text-xs text-muted-foreground'>Distance (28d)</p>
              <p className='text-lg font-semibold'>{distance28d.toFixed(1)} km</p>
            </div>
            <div className='rounded-xl border border-border p-3'>
              <p className='text-xs text-muted-foreground'>Weekly run/swim/ride</p>
              <p className='text-sm font-semibold'>{weeklyCounts.run}/{goal.weekly_activity_goal_run || 0} | {weeklyCounts.swim}/{goal.weekly_activity_goal_swim || 0} | {weeklyCounts.ride}/{goal.weekly_activity_goal_ride || 0}</p>
            </div>
          </div>
        </div>
      </Card>

      <Card className='p-6'>
        <div className='flex items-center justify-between'>
          <p className='text-lg font-semibold'>Upcoming Activities</p>
          <p className='text-sm text-muted-foreground'>{(weekPlan?.week_start || '')} - {(weekPlan?.week_end || '')}</p>
        </div>
        {upcoming.length === 0 ? (
          <p className='mt-3 text-sm text-muted-foreground'>No planned sessions for the remaining days of this week.</p>
        ) : (
          <div className='mt-4 grid gap-3 md:grid-cols-2'>
            {upcoming.map((s, idx) => (
              <button
                key={`${s.date}-${idx}`}
                type='button'
                className='rounded-xl border border-border bg-muted/20 p-4 text-left transition hover:border-cyan-400/50 hover:bg-cyan-500/5'
                onClick={() => navigate(`/plan/workouts/${s.date}/${idx}`)}
              >
                <div className='flex items-center justify-between'>
                  <div className='flex items-center gap-2'>
                    <span className='grid h-8 w-8 place-items-center rounded-full border border-border bg-background/60'>
                      {sportIcon(s.sport)}
                    </span>
                    <div>
                      <p className='font-semibold'>{s.title || `${s.sport} workout`}</p>
                      <p className='text-xs text-muted-foreground'>{s.date} | {s.workout_type || 'aerobic'}</p>
                    </div>
                  </div>
                  <Target className='h-4 w-4 text-emerald-300' />
                </div>
                <div className='mt-3 flex flex-wrap items-center gap-2 text-xs'>
                  <span className='rounded-lg border border-border px-2 py-1'>{s.distance_km ?? '--'} km</span>
                  <span className='rounded-lg border border-border px-2 py-1'>{s.duration_min ?? '--'} min</span>
                  <span className='rounded-lg border border-border px-2 py-1'>{s.hr_zone || 'Z2'}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
