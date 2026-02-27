import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { Bike, PersonStanding, Target, Waves } from '../components/ui/icons';
import { api } from '../lib/api';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';

type PlannedSession = {
  date: string;
  sport: string;
  duration_min?: number;
  distance_km?: number;
  hr_zone?: string;
  title?: string;
  workout_type?: string;
  coach_notes?: string;
  status?: 'planned' | 'done' | 'missed';
};

type WeekPlan = {
  week_start?: string;
  week_end?: string;
  days?: PlannedSession[];
};

function sportIcon(sport = '') {
  const s = sport.toLowerCase();
  if (s.includes('swim')) return <Waves className='h-4 w-4 text-cyan-300' />;
  if (s.includes('ride') || s.includes('bike') || s.includes('cycle')) return <Bike className='h-4 w-4 text-sky-300' />;
  return <PersonStanding className='h-4 w-4 text-rose-300' />;
}

export function PlanWorkoutPage() {
  const navigate = useNavigate();
  const params = useParams();
  const date = params.date || '';
  const idx = Number(params.idx || 0);

  const { data: weekPlan } = useQuery<WeekPlan>({
    queryKey: ['plan-current-week'],
    queryFn: async () => (await api.get('/plan/current-week')).data,
  });

  const session = useMemo(() => {
    const sameDay = ((weekPlan?.days || []) as PlannedSession[]).filter((d) => d.date === date);
    return sameDay[idx] || null;
  }, [weekPlan?.days, date, idx]);

  if (!session) {
    return (
      <Card className='p-6'>
        <p className='text-xl font-semibold'>Workout not found</p>
        <p className='mt-2 text-sm text-muted-foreground'>This planned session is not available in the current week plan.</p>
        <Button className='mt-4' onClick={() => navigate('/plan')}>Back to plan</Button>
      </Card>
    );
  }

  return (
    <div className='space-y-4'>
      <Card className='p-6'>
        <div className='flex items-center justify-between'>
          <div className='flex items-center gap-3'>
            <span className='grid h-10 w-10 place-items-center rounded-full border border-border bg-muted/20'>
              {sportIcon(session.sport)}
            </span>
            <div>
              <p className='text-2xl font-semibold'>{session.title || `${session.sport} workout`}</p>
              <p className='text-sm text-muted-foreground'>{session.date} | {session.workout_type || 'aerobic'} | status: {session.status || 'planned'}</p>
            </div>
          </div>
          <Button variant='outline' onClick={() => navigate('/plan')}>Back to plan</Button>
        </div>

        <div className='mt-5 grid gap-3 md:grid-cols-4'>
          <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Distance</p><p className='text-xl font-semibold'>{session.distance_km ?? '--'} km</p></div>
          <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Duration</p><p className='text-xl font-semibold'>{session.duration_min ?? '--'} min</p></div>
          <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>HR target</p><p className='text-xl font-semibold'>{session.hr_zone || 'Z2'}</p></div>
          <div className='rounded-xl border border-border p-3'><p className='text-xs text-muted-foreground'>Workout type</p><p className='text-xl font-semibold'>{session.workout_type || 'aerobic'}</p></div>
        </div>
      </Card>

      <Card className='p-6'>
        <div className='flex items-center gap-2'>
          <Target className='h-4 w-4 text-emerald-300' />
          <p className='text-lg font-semibold'>Coach Brief</p>
        </div>
        <p className='mt-3 rounded-xl border border-cyan-400/30 bg-cyan-500/10 p-3 text-sm text-cyan-100'>
          {session.coach_notes || 'Execute with control, hold target intensity, and finish with clean technique.'}
        </p>
      </Card>
    </div>
  );
}
