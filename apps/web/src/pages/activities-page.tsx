import { Bike, PersonStanding, Search, Waves } from '../components/ui/icons';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { Activity, formatDuration, formatPace, km, pacePerKm } from '../lib/analytics';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { EmptyState } from '../components/ui/empty-state';
import { Skeleton } from '../components/ui/skeleton';

function SportIcon({ type }: { type: string }) {
  const lower = type.toLowerCase();
  if (lower.includes('run')) return <PersonStanding className='h-8 w-8 text-red-400' />;
  if (lower.includes('ride') || lower.includes('bike')) return <Bike className='h-8 w-8 text-sky-400' />;
  if (lower.includes('swim')) return <Waves className='h-8 w-8 text-cyan-300' />;
  return <PersonStanding className='h-8 w-8 text-zinc-400' />;
}

function kudosAvatarUrl(k: any): string {
  return String(k?.avatar_url || k?.profile_medium || k?.profile || k?.avatar || k?.picture || '').trim();
}

export function ActivitiesPage() {
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const { data, isLoading } = useQuery<Activity[]>({ queryKey: ['activities'], queryFn: async () => (await api.get('/activities')).data });

  const filtered = useMemo(() => {
    return (data || []).filter((a) => {
      const matchesText = query ? a.name.toLowerCase().includes(query.toLowerCase()) : true;
      const matchesType = type === 'all' ? true : a.type.toLowerCase() === type;
      return matchesText && matchesType;
    });
  }, [data, query, type]);

  if (isLoading) {
    return <div className='grid gap-4 md:grid-cols-2'>{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className='h-44' />)}</div>;
  }
  if (!data?.length) return <EmptyState />;

  return (
    <div className='space-y-4'>
      <Card className='p-5'>
        <div className='grid gap-3 md:grid-cols-[minmax(260px,420px)_1fr] md:items-center'>
          <div className='relative md:max-w-[420px]'>
            <Search className='absolute left-3 top-3 h-5 w-5 text-muted-foreground' />
            <Input className='pl-10 text-base' placeholder='Search activity name' value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className='flex flex-wrap items-center gap-2 md:justify-end'>
            {['all', 'run', 'ride', 'swim'].map((t) => (
              <button key={t} type='button' onClick={() => setType(t)} className={`rounded-xl border px-4 py-2 text-base ${type === t ? 'border-primary bg-primary/10' : 'border-border bg-background'}`}>
                {t.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </Card>

      <div className='space-y-6 py-2'>
        {filtered.map((activity) => (
          <Link key={activity.id} to={`/activities/${activity.id}`}>
            {(() => {
              const highlighted = Array.isArray(activity.highlighted_kudosers) ? activity.highlighted_kudosers : [];
              const preview = Array.isArray(activity.kudos_preview) ? activity.kudos_preview : [];
              const merged = [...highlighted, ...preview];
              const byKey = new Map<string, any>();
              for (let i = 0; i < merged.length; i += 1) {
                const item = merged[i];
                if (!item || typeof item !== 'object') continue;
                const key = String(item.id ?? item.athlete_id ?? item.display_name ?? `${i}`);
                if (!byKey.has(key)) byKey.set(key, item);
              }
              const kudoers = Array.from(byKey.values()).slice(0, 6);
              return (
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
                  <p className='text-xs uppercase tracking-wide text-muted-foreground'>
                    {String(activity.type || '').toLowerCase().includes('swim') ? 'Average 100m' : 'Avg Pace'}
                  </p>
                  <p className='text-xl font-semibold'>
                    {String(activity.type || '').toLowerCase().includes('swim')
                      ? `${formatDuration(
                          activity.distance_m > 0 ? (activity.moving_time_s / (activity.distance_m / 100)) : 0
                        )} /100m`
                      : formatPace(pacePerKm(activity.distance_m, activity.moving_time_s))}
                  </p>
                </div>
              </div>
              {(kudoers.length > 0) && (
                <div className='mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground'>
                  <span className='font-medium'>Kudoers:</span>
                  {kudoers.map((k: any, idx: number) => {
                    const img = kudosAvatarUrl(k);
                    const label = k?.display_name || `${k?.firstname || ''} ${k?.lastname || ''}`.trim() || `Athlete ${idx + 1}`;
                    return (
                      <span key={`${k?.id || k?.athlete_id || idx}`} className='inline-flex items-center gap-1 rounded-full border border-border px-2 py-1'>
                        {img ? (
                          <img src={img} alt={label} className='h-5 w-5 rounded-full object-cover' />
                        ) : (
                          <span className='grid h-5 w-5 place-items-center rounded-full bg-muted text-[10px] text-foreground'>
                            {label.slice(0, 1).toUpperCase()}
                          </span>
                        )}
                        <span>{label}</span>
                      </span>
                    );
                  })}
                </div>
              )}
            </Card>
              );
            })()}
          </Link>
        ))}
      </div>
    </div>
  );
}
