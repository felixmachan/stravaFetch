import { Bike, PersonStanding, Search, Waves } from '../components/ui/icons';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { Activity, formatDuration, formatPace, km, pacePerKm } from '../lib/analytics';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { EmptyState } from '../components/ui/empty-state';

function SportIcon({ type }: { type: string }) {
  const lower = type.toLowerCase();
  if (lower.includes('run')) return <PersonStanding className='h-8 w-8 text-red-400' />;
  if (lower.includes('ride') || lower.includes('bike')) return <Bike className='h-8 w-8 text-sky-400' />;
  if (lower.includes('swim')) return <Waves className='h-8 w-8 text-cyan-300' />;
  return <PersonStanding className='h-8 w-8 text-zinc-400' />;
}

export function ActivitiesPage() {
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const { data } = useQuery<Activity[]>({ queryKey: ['activities'], queryFn: async () => (await api.get('/activities')).data });

  const filtered = useMemo(() => {
    return (data || []).filter((a) => {
      const matchesText = query ? a.name.toLowerCase().includes(query.toLowerCase()) : true;
      const matchesType = type === 'all' ? true : a.type.toLowerCase() === type;
      return matchesText && matchesType;
    });
  }, [data, query, type]);

  if (!data?.length) return <EmptyState />;

  return (
    <div className='space-y-4'>
      <Card className='p-5'>
        <div className='grid gap-3 md:grid-cols-[1fr_auto_auto_auto]'>
          <div className='relative'>
            <Search className='absolute left-3 top-3 h-5 w-5 text-muted-foreground' />
            <Input className='pl-10 text-base' placeholder='Search activity name' value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          {['all', 'run', 'ride', 'swim'].map((t) => (
            <button key={t} type='button' onClick={() => setType(t)} className={`rounded-xl border px-4 py-2 text-base ${type === t ? 'border-primary bg-primary/10' : 'border-border bg-background'}`}>
              {t.toUpperCase()}
            </button>
          ))}
        </div>
      </Card>

      <div className='space-y-6 py-2'>
        {filtered.map((activity) => (
          <Link key={activity.id} to={`/activities/${activity.id}`}>
            <Card className='p-6 transition hover:-translate-y-0.5 hover:border-primary/50 mb-4'>
              <div className='grid grid-cols-[auto_1fr_auto] items-center gap-4'>
                <div className='grid h-14 w-14 place-items-center rounded-2xl border border-border bg-background/60'>
                  <SportIcon type={activity.type} />
                </div>
                <div>
                  <p className='text-2xl font-semibold'>{activity.name}</p>
                  <p className='text-base text-muted-foreground'>{new Date(activity.start_date).toLocaleString()}</p>
                </div>
                <div className='text-right text-sm text-muted-foreground'>#{activity.id}</div>
              </div>
              <div className='mt-4 grid grid-cols-3 gap-3 text-base'>
                <div>
                  <p className='text-xs uppercase tracking-wide text-muted-foreground'>Distance</p>
                  <p className='text-xl font-semibold'>{km(activity.distance_m).toFixed(2)} km</p>
                </div>
                <div>
                  <p className='text-xs uppercase tracking-wide text-muted-foreground'>Time</p>
                  <p className='text-xl font-semibold'>{formatDuration(activity.moving_time_s)}</p>
                </div>
                <div>
                  <p className='text-xs uppercase tracking-wide text-muted-foreground'>Avg Pace</p>
                  <p className='text-xl font-semibold'>{formatPace(pacePerKm(activity.distance_m, activity.moving_time_s))}</p>
                </div>
              </div>
              <div className='mt-3 flex flex-wrap gap-2 text-xs'>
                <span className='rounded-lg border border-border px-2 py-1 text-muted-foreground'>
                  Achievements: {Number(activity.achievement_count || activity?.raw_payload?.achievement_count || 0)}
                </span>
                <span className='rounded-lg border border-border px-2 py-1 text-muted-foreground'>
                  Kudos: {Number(activity.kudos_count || activity?.raw_payload?.kudos_count || 0)}
                </span>
                <span className='rounded-lg border border-border px-2 py-1 text-muted-foreground'>
                  Power: {(activity.average_watts ?? activity?.raw_payload?.average_watts) ? `${Math.round(Number(activity.average_watts ?? activity?.raw_payload?.average_watts))} W` : 'n/a'}
                </span>
                <span className='rounded-lg border border-border px-2 py-1 text-muted-foreground'>
                  Sync: {activity.fully_synced ? 'Detailed' : 'Summary'}
                </span>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
