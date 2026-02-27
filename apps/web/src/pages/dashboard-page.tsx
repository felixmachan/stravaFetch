import { Bike, HeartPulse, PersonStanding, Waves } from '../components/ui/icons';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { LatLngBounds } from 'leaflet';
import { MapContainer, Polyline, TileLayer, useMap } from 'react-leaflet';
import { api } from '../lib/api';
import {
  Activity,
  formatDuration,
  formatPace,
  getWeekRange,
  groupActivitiesByDay,
  groupByWeek,
  km,
  pacePerKm,
  weeklyActivityCountsBySport,
  weeklyDistanceBySport,
} from '../lib/analytics';
import { decodePolyline } from '../lib/polyline';
import { Card, CardTitle, CardValue } from '../components/ui/card';
import { EmptyState } from '../components/ui/empty-state';
import { Skeleton } from '../components/ui/skeleton';

type GoalPayload = {
  weekly_activity_goal_total?: number;
  weekly_activity_goal_run?: number;
  weekly_activity_goal_swim?: number;
  weekly_activity_goal_ride?: number;
};

type PlannedSession = {
  date: string;
  sport: string;
  duration_min?: number;
  distance_km?: number;
  hr_zone?: string;
  title?: string;
  status?: 'planned' | 'done' | 'missed';
};

type WeekPlan = {
  week_start?: string;
  week_end?: string;
  days?: PlannedSession[];
};

type NextWorkout = PlannedSession;

function FitRouteBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  if (points.length > 1) {
    map.fitBounds(new LatLngBounds(points), { padding: [24, 24], maxZoom: 14 });
  }
  return null;
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className='rounded-xl border border-border bg-slate-950/95 p-3 text-sm shadow-2xl backdrop-blur'>
      <p className='font-semibold text-slate-100'>{label}</p>
      <div className='mt-2 space-y-1'>
        {payload.map((entry: any, idx: number) => (
          <p key={idx} style={{ color: entry.color }} className='font-medium'>
            {entry.name}: <span className='text-slate-100'>{Number(entry.value).toFixed(1)}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

function dayLabel(d: Date) {
  return d.toLocaleDateString(undefined, { weekday: 'short' });
}

function monthDays(base: Date) {
  const first = new Date(base.getFullYear(), base.getMonth(), 1);
  const last = new Date(base.getFullYear(), base.getMonth() + 1, 0);
  const days = [];
  for (let i = 1; i <= last.getDate(); i += 1) days.push(new Date(base.getFullYear(), base.getMonth(), i));
  const pad = first.getDay() === 0 ? 6 : first.getDay() - 1;
  return { days, pad };
}

function SportIcons({ items }: { items: Activity[] }) {
  const hasRun = items.some((a) => (a.type || '').toLowerCase().includes('run'));
  const hasSwim = items.some((a) => (a.type || '').toLowerCase().includes('swim'));
  const hasRide = items.some((a) => (a.type || '').toLowerCase().includes('ride'));

  return (
    <div className='mt-2 flex items-center gap-1.5'>
      {hasRun && (
        <span className='grid h-7 w-7 place-items-center rounded-full border border-rose-400/40 bg-rose-500/12'>
          <PersonStanding className='h-4 w-4 text-rose-300' />
        </span>
      )}
      {hasSwim && (
        <span className='grid h-7 w-7 place-items-center rounded-full border border-cyan-400/40 bg-cyan-500/12'>
          <Waves className='h-4 w-4 text-cyan-300' />
        </span>
      )}
      {hasRide && (
        <span className='grid h-7 w-7 place-items-center rounded-full border border-sky-400/40 bg-sky-500/12'>
          <Bike className='h-4 w-4 text-sky-300' />
        </span>
      )}
    </div>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery<Activity[]>({ queryKey: ['activities'], queryFn: async () => (await api.get('/activities')).data });
  const { data: goal } = useQuery<GoalPayload>({ queryKey: ['goal'], queryFn: async () => (await api.get('/goal')).data });
  const { data: weekPlan } = useQuery<WeekPlan>({ queryKey: ['plan-current-week'], queryFn: async () => (await api.get('/plan/current-week')).data });
  const { data: nextWorkout } = useQuery<NextWorkout>({ queryKey: ['next-workout'], queryFn: async () => (await api.get('/next-workout')).data });
  const { data: coachToneData } = useQuery<{ response_text?: string }>({ queryKey: ['coach-tone'], queryFn: async () => (await api.get('/coach-tone')).data });
  const { data: aiHistory } = useQuery({
    queryKey: ['ai-history-weekly-opinion'],
    queryFn: async () =>
      (await api.get('/ai/history', { params: { mode: 'coach_tone' } })).data as Array<{
        id: number;
        question: string;
        response_text: string;
        created_at: string;
      }>,
  });
  const [weeklyOpinionTarget, setWeeklyOpinionTarget] = useState('');
  const [weeklyOpinionTyped, setWeeklyOpinionTyped] = useState('');
  const [weeklyCursorOn, setWeeklyCursorOn] = useState(true);
  const weeklyIsTyping = Boolean(weeklyOpinionTarget) && weeklyOpinionTyped.length < weeklyOpinionTarget.length;
  const [showMonth, setShowMonth] = useState(false);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  const latest = data?.[0];
  const trends = useMemo(() => groupByWeek(data || [], 28), [data]);
  const week = useMemo(() => getWeekRange(new Date()), []);
  const byDay = useMemo(() => groupActivitiesByDay(data || [], week), [data, week]);
  const weeklyDistance = useMemo(() => weeklyDistanceBySport(data || [], week), [data, week]);
  const weeklyCount = useMemo(() => weeklyActivityCountsBySport(data || [], week), [data, week]);
  const month = useMemo(() => monthDays(selectedDate || new Date()), [selectedDate]);
  const plannedByDay = useMemo(() => {
    const map: Record<string, PlannedSession[]> = {};
    for (const s of weekPlan?.days || []) {
      if (!s?.date) continue;
      if (!map[s.date]) map[s.date] = [];
      map[s.date].push(s);
    }
    return map;
  }, [weekPlan]);

  useEffect(() => {
    if (weeklyOpinionTarget) return;
    const latest = (aiHistory || [])[0];
    if (latest?.response_text) {
      setWeeklyOpinionTarget(latest.response_text);
      setWeeklyOpinionTyped(latest.response_text);
      return;
    }
    if (coachToneData?.response_text) {
      setWeeklyOpinionTarget(coachToneData.response_text);
      setWeeklyOpinionTyped(coachToneData.response_text);
    }
  }, [aiHistory, coachToneData?.response_text, weeklyOpinionTarget]);

  useEffect(() => {
    if (!weeklyOpinionTarget) return;
    if (weeklyOpinionTyped.length >= weeklyOpinionTarget.length) return;
    const t = setTimeout(() => {
      const nextLen = Math.min(weeklyOpinionTarget.length, weeklyOpinionTyped.length + 2);
      setWeeklyOpinionTyped(weeklyOpinionTarget.slice(0, nextLen));
    }, 18);
    return () => clearTimeout(t);
  }, [weeklyOpinionTarget, weeklyOpinionTyped]);

  useEffect(() => {
    if (!weeklyIsTyping) return;
    const t = setInterval(() => setWeeklyCursorOn((v) => !v), 450);
    return () => clearInterval(t);
  }, [weeklyIsTyping]);

  if (isLoading) {
    return <div className='grid gap-4 md:grid-cols-3'>{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className='h-32' />)}</div>;
  }
  if (!data?.length) return <EmptyState />;

  const routePoints = Array.isArray(latest?.raw_payload?.map?.polyline_points)
    ? latest.raw_payload.map.polyline_points
    : latest?.map_summary_polyline
      ? decodePolyline(latest.map_summary_polyline)
      : [];

  const goalTotal = Number(goal?.weekly_activity_goal_total || 0);
  const goalRun = Number(goal?.weekly_activity_goal_run || 0);
  const goalSwim = Number(goal?.weekly_activity_goal_swim || 0);
  const goalRide = Number(goal?.weekly_activity_goal_ride || 0);

  return (
    <div className='space-y-4'>
      <Card className='p-5'>
        <div className='flex items-center justify-between'>
          <p className='text-lg font-semibold'>Weekly Calendar</p>
          <button className='text-sm text-cyan-300 hover:underline' onClick={() => setShowMonth(true)}>Open month</button>
        </div>
        <div className='mt-3 grid gap-2 md:grid-cols-7'>
          {week.days.map((d) => {
            const key = d.toISOString().slice(0, 10);
            const items = byDay[key] || [];
            const planned = plannedByDay[key] || [];
            return (
              <button
                key={key}
                className='rounded-xl border border-border bg-muted/20 p-3 text-left transition hover:border-cyan-400/50'
                onClick={() => {
                  setSelectedDate(d);
                  setShowMonth(true);
                }}
              >
                <p className='text-xs text-muted-foreground'>{dayLabel(d)}</p>
                <p className='text-lg font-semibold'>{d.getDate()}</p>
                <p className='text-xs text-muted-foreground'>{items.length} session{items.length === 1 ? '' : 's'}</p>
                <SportIcons items={items} />
                {planned.length > 0 && (
                  <div className='mt-2 flex items-center gap-1'>
                    {planned.slice(0, 3).map((p, i) => (
                      <span
                        key={`${key}-${i}`}
                        className={`grid h-5 w-5 place-items-center rounded-full text-[10px] font-semibold ${
                          p.status === 'done'
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : p.status === 'missed'
                              ? 'bg-rose-500/20 text-rose-300'
                              : 'bg-slate-500/20 text-slate-200'
                        }`}
                        title={`${p.title || p.sport} (${p.status || 'planned'})`}
                      >
                        {p.status === 'done' ? 'OK' : p.status === 'missed' ? 'X' : 'o'}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </Card>


      <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-4'>
        <Card>
          <CardTitle>Weekly Distance</CardTitle>
          <CardValue>{weeklyDistance.total.toFixed(1)} km</CardValue>
          <p className='mt-1 text-sm text-muted-foreground'>Run {weeklyDistance.run.toFixed(1)} | Swim {weeklyDistance.swim.toFixed(1)} | Ride {weeklyDistance.ride.toFixed(1)}</p>
        </Card>
        <Card>
          <CardTitle>Weekly Activity Goal</CardTitle>
          <CardValue>{weeklyCount.total}/{goalTotal || '--'}</CardValue>
          <p className='text-sm text-muted-foreground'>Run {weeklyCount.run}/{goalRun || 0} | Swim {weeklyCount.swim}/{goalSwim || 0} | Ride {weeklyCount.ride}/{goalRide || 0}</p>
        </Card>        <Card>
          <CardTitle>Avg Pace</CardTitle>
          <CardValue>{formatPace(pacePerKm(latest?.distance_m, latest?.moving_time_s))}</CardValue>
          <p className='text-sm text-muted-foreground'>Latest workout rhythm</p>
        </Card>
        <Card>
          <CardTitle>Next Workout</CardTitle>
          <CardValue>{nextWorkout?.title || (nextWorkout?.sport ? `${nextWorkout.sport} session` : 'n/a')}</CardValue>
          <p className='text-sm text-muted-foreground'>
            {nextWorkout?.date || 'No planned date'} | {nextWorkout?.distance_km ?? '--'} km | {nextWorkout?.duration_min ?? '--'} min | {nextWorkout?.hr_zone || 'n/a'}
          </p>
        </Card>
      </div>

      <div className='grid gap-4 md:grid-cols-2'>
        <Card className='h-80'>
          <CardTitle>Weekly Distance by Sport</CardTitle>
          <div className='mt-3 h-[250px]'>
            <ResponsiveContainer width='100%' height='100%'>
              <BarChart data={trends} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <defs>
                  <linearGradient id='runFill' x1='0' y1='0' x2='0' y2='1'><stop offset='0%' stopColor='#34d399' stopOpacity={0.95} /><stop offset='100%' stopColor='#34d399' stopOpacity={0.3} /></linearGradient>
                  <linearGradient id='rideFill' x1='0' y1='0' x2='0' y2='1'><stop offset='0%' stopColor='#38bdf8' stopOpacity={0.95} /><stop offset='100%' stopColor='#38bdf8' stopOpacity={0.3} /></linearGradient>
                  <linearGradient id='swimFill' x1='0' y1='0' x2='0' y2='1'><stop offset='0%' stopColor='#818cf8' stopOpacity={0.95} /><stop offset='100%' stopColor='#818cf8' stopOpacity={0.3} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray='3 3' stroke='hsl(var(--border))' />
                <XAxis dataKey='week' tick={{ fontSize: 11 }} interval='preserveStartEnd' minTickGap={24} />
                <YAxis />
                <Tooltip content={<ChartTooltip />} />
                <Legend verticalAlign='bottom' height={20} wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey='run' name='run' stackId='a' fill='url(#runFill)' radius={[6, 6, 0, 0]} />
                <Bar dataKey='ride' name='ride' stackId='a' fill='url(#rideFill)' radius={[6, 6, 0, 0]} />
                <Bar dataKey='swim' name='swim' stackId='a' fill='url(#swimFill)' radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className='h-80'>
          <CardTitle>Training Load Trend (28d)</CardTitle>
          <div className='mt-3 h-[250px]'>
            <ResponsiveContainer width='100%' height='100%'>
              <LineChart data={trends} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <defs>
                  <filter id='loadGlow' x='-60%' y='-60%' width='220%' height='220%'><feGaussianBlur stdDeviation='2.5' result='blur' /><feMerge><feMergeNode in='blur' /><feMergeNode in='SourceGraphic' /></feMerge></filter>
                </defs>
                <CartesianGrid strokeDasharray='3 3' stroke='hsl(var(--border))' />
                <XAxis dataKey='week' tick={{ fontSize: 11 }} interval='preserveStartEnd' minTickGap={24} />
                <YAxis />
                <Tooltip content={<ChartTooltip />} />
                <Line type='monotone' dataKey='load' name='load' stroke='#34d399' strokeWidth={3} dot={false} filter='url(#loadGlow)' />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className='grid gap-4 md:grid-cols-2'>
        <Card className='h-[360px]'>
          <CardTitle>Last Activity</CardTitle>
          <p className='mt-2 text-lg font-semibold'>{latest?.name || 'n/a'}</p>
          <div className='mt-3 grid gap-2 sm:grid-cols-4'>
            <div className='rounded-xl border border-border p-2'>
              <p className='text-xs text-muted-foreground'>Type</p>
              <p className='text-sm font-semibold'>{latest?.type || 'n/a'}</p>
            </div>
            <div className='rounded-xl border border-border p-2'>
              <p className='text-xs text-muted-foreground'>Time</p>
              <p className='text-sm font-semibold'>{formatDuration(latest?.moving_time_s || 0)}</p>
            </div>
            <div className='rounded-xl border border-border p-2'>
              <p className='text-xs text-muted-foreground'>Distance</p>
              <p className='text-sm font-semibold'>{km(latest?.distance_m || 0).toFixed(2)} km</p>
            </div>
            <div className='rounded-xl border border-border p-2'>
              <p className='text-xs text-muted-foreground'>Avg HR</p>
              <p className='text-sm font-semibold'>{latest?.avg_hr ? Math.round(latest.avg_hr) : 'n/a'}</p>
            </div>
          </div>
          <div className='mt-3 h-[230px] overflow-hidden rounded-xl'>
            {routePoints.length > 1 ? (
              <MapContainer center={routePoints[0]} zoom={12} style={{ height: '100%' }}>
                <FitRouteBounds points={routePoints} />
                <TileLayer url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' />
                <Polyline positions={routePoints} pathOptions={{ color: '#ef4444', weight: 4 }} />
              </MapContainer>
            ) : (
              <div className='grid h-full place-items-center rounded-xl bg-muted text-sm text-muted-foreground'>No map data available.</div>
            )}
          </div>
        </Card>
        <Card>
          <CardTitle>AI Weekly Progress</CardTitle>
          <div className='mt-3 space-y-3 text-sm'>
            <div className='rounded-xl border border-border p-3 text-sm text-muted-foreground'>
              {weeklyOpinionTarget ? (
                <p className='text-sm text-cyan-100'>
                  {weeklyOpinionTyped}
                  {weeklyIsTyping ? <span className={`${weeklyCursorOn ? 'opacity-100' : 'opacity-0'} transition-opacity`}>|</span> : null}
                </p>
              ) : (
                'No AI weekly opinion generated yet.'
              )}
            </div>
          </div>
        </Card>
      </div>

      {showMonth && (
        <div className='fixed inset-0 z-[2200] grid place-items-center bg-slate-950/70 p-4' onClick={() => setShowMonth(false)}>
          <div className='w-full max-w-3xl rounded-2xl border border-border bg-background p-4 shadow-2xl' onClick={(e) => e.stopPropagation()}>
            <div className='mb-3 flex items-center justify-between'>
              <p className='text-lg font-semibold'>{(selectedDate || new Date()).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</p>
              <button className='text-sm text-muted-foreground hover:text-foreground' onClick={() => setShowMonth(false)}>Close</button>
            </div>
            <div className='mb-2 grid grid-cols-7 gap-2 text-xs text-muted-foreground'>
              <span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span>
            </div>
            <div className='grid grid-cols-7 gap-2'>
              {Array.from({ length: month.pad }).map((_, i) => <div key={`pad-${i}`} />)}
              {month.days.map((d) => {
                const key = d.toISOString().slice(0, 10);
                const items = (data || []).filter((a) => new Date(a.start_date).toISOString().slice(0, 10) === key);
                const planned = (weekPlan?.days || []).filter((s) => s.date === key);
                const active = selectedDate && selectedDate.toISOString().slice(0, 10) === key;
                return (
                  <button
                    key={key}
                    className={`rounded-xl border p-2 text-left ${active ? 'border-cyan-400/60 bg-cyan-500/10' : 'border-border bg-muted/20'}`}
                    onClick={() => setSelectedDate(d)}
                  >
                    <p className='text-sm font-semibold'>{d.getDate()}</p>
                    <p className='text-xs text-muted-foreground'>{items.length}</p>
                    <SportIcons items={items} />
                    {planned.length > 0 && (
                      <div className='mt-1 flex items-center gap-1'>
                        {planned.slice(0, 2).map((p, idx) => (
                          <span key={idx} className='text-[10px] text-muted-foreground'>
                            {p.status === 'done' ? 'OK' : p.status === 'missed' ? 'X' : 'o'} {p.sport}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
            <div className='mt-4 rounded-xl border border-border p-3'>
              <p className='text-sm font-semibold'>
                {selectedDate ? selectedDate.toLocaleDateString() : 'Select a day'}
              </p>
              <div className='mt-2 space-y-2 text-sm'>
                {selectedDate &&
                  (data || [])
                    .filter((a) => new Date(a.start_date).toISOString().slice(0, 10) === selectedDate.toISOString().slice(0, 10))
                    .map((a) => (
                      <button
                        key={a.id}
                        type='button'
                        className='flex w-full items-center justify-between rounded-lg border border-border p-2 text-left transition hover:border-cyan-400/50 hover:bg-cyan-500/5'
                        onClick={() => {
                          setShowMonth(false);
                          navigate(`/activities/${a.id}`);
                        }}
                      >
                        <span>{a.name} ({a.type})</span>
                        <span className='text-muted-foreground'>{km(a.distance_m).toFixed(1)} km | {formatDuration(a.moving_time_s)}</span>
                      </button>
                    ))}
                {selectedDate &&
                  ((weekPlan?.days || []).filter((p) => p.date === selectedDate.toISOString().slice(0, 10))).map((p, idx) => (
                    <div key={`planned-${idx}`} className='flex items-center justify-between rounded-lg border border-border bg-muted/20 p-2'>
                      <span>Planned: {p.title || p.sport}</span>
                      <span className='text-muted-foreground'>{p.duration_min ?? '--'} min | {p.distance_km ?? '--'} km | {p.hr_zone || 'n/a'} | {p.status || 'planned'}</span>
                    </div>
                  ))}
                {selectedDate &&
                  (data || []).filter((a) => new Date(a.start_date).toISOString().slice(0, 10) === selectedDate.toISOString().slice(0, 10)).length === 0 && (
                    <p className='text-muted-foreground'>No workouts on this day.</p>
                  )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}




