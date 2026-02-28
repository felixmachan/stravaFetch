import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bike, HeartPulse, Shoe, Target, UserCircle2 } from '../components/ui/icons';
import { useAuth } from '../context/auth-context';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';

type ProfilePayload = {
  display_name?: string;
  primary_sport?: string;
  height_cm?: number;
  weight_kg?: number;
  weekly_target_hours?: number;
  hr_zones?: Array<{ index?: number; min?: number; max?: number }>;
  personal_records?: Array<{
    effort_key?: string;
    effort_label?: string;
    distance_m?: number | null;
    records?: Array<{
      rank?: number;
      elapsed_time_s?: number;
      achieved_at?: string | null;
      activity_id?: number | null;
      activity_name?: string;
    }>;
  }>;
  schedule?: Record<string, any>;
};

type GearItem = {
  id?: string;
  name?: string;
  distance?: number;
  primary?: boolean;
  brand_name?: string;
  model_name?: string;
  description?: string;
};

export function ProfilePage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['profile'],
    queryFn: async () => (await api.get('/profile')).data as ProfilePayload,
  });
  const [form, setForm] = useState<ProfilePayload>({});
  const [editZones, setEditZones] = useState(false);
  const [zoneDraft, setZoneDraft] = useState<Array<{ index: number; min: number; max: number }>>([]);

  useEffect(() => {
    if (data) {
      setForm(data);
      const normalized = Array.from({ length: 5 }).map((_, i) => {
        const z = (data.hr_zones || [])[i] || {};
        return { index: i + 1, min: Number(z.min ?? (i === 0 ? 100 : 120 + i * 10)), max: Number(z.max ?? (i === 4 ? -1 : 129 + i * 10)) };
      });
      setZoneDraft(normalized);
    }
  }, [data]);

  const save = useMutation({
    mutationFn: async () => api.patch('/profile', form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profile'] });
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Profile saved', message: 'Your training profile is updated.' } }));
    },
  });
  const saveZones = useMutation({
    mutationFn: async () => (await api.patch('/profile', { hr_zones: zoneDraft })).data,
    onSuccess: (res) => {
      setEditZones(false);
      qc.invalidateQueries({ queryKey: ['profile'] });
      qc.invalidateQueries({ queryKey: ['activities'] });
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: 'HR zones updated',
            message: `Recalculated activities: ${res?.recalculated_hr_metrics ?? 0}`,
          },
        })
      );
    },
  });
  const syncStravaProfile = useMutation({
    mutationFn: async () => (await api.post('/auth/strava/sync-profile', {}, { suppressToast: true } as any)).data,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['profile'] });
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            type: 'success',
            title: 'Strava profile synced',
            message: `Zones: ${res?.hr_zones_count ?? 0}, status: ${res?.hr_zones_status ?? 'ok'}`,
          },
        })
      );
    },
    onError: (err: any) => {
      const resp = err?.response?.data || {};
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            type: 'error',
            title: 'Strava profile sync failed',
            message: `Zones: ${resp?.hr_zones_count ?? 0}, status: ${resp?.hr_zones_status ?? 'unknown'}${resp?.detail ? `, ${resp.detail}` : ''}`,
          },
        })
      );
    },
  });

  const profileComplete = useMemo(() => Boolean(form.primary_sport && form.height_cm && form.weight_kg), [form]);
  const set = (key: keyof ProfilePayload, value: any) => setForm((p) => ({ ...p, [key]: value }));
  const zoneColors = ['#34d399', '#22d3ee', '#facc15', '#fb923c', '#f43f5e'];
  const profileImage = form.schedule?.strava_profile_medium || form.schedule?.strava_profile || '';
  const birthDate = form.schedule?.strava_birthdate || form.schedule?.birth_date || 'Not available';
  const bikes: GearItem[] = form.schedule?.strava_gear?.bikes || [];
  const shoes: GearItem[] = form.schedule?.strava_gear?.shoes || [];
  const personalRecords = Array.isArray(form.personal_records) ? form.personal_records : [];
  const displayName = form.display_name || `${user?.username || 'Athlete'}`;
  const km = (m?: number) => `${((Number(m) || 0) / 1000).toFixed(1)} km`;

  return (
    <div className='space-y-4'>
      <Card className='bg-gradient-to-r from-red-500/10 to-cyan-500/10 p-6'>
        <p className='flex items-center gap-2 text-2xl font-semibold'><UserCircle2 className='h-5 w-5 text-cyan-300' />Athlete Identity</p>
        <p className='mt-1 text-base text-muted-foreground'>Identity fields are synced from account and Strava.</p>
        <div className='mt-4 flex flex-wrap items-start gap-4 lg:flex-nowrap'>
          <div className='flex min-w-[280px] items-center gap-4'>
            <div className='h-16 w-16 overflow-hidden rounded-2xl border border-border bg-muted'>
              {profileImage ? (
                <img src={profileImage} alt={displayName} className='h-full w-full object-cover' />
              ) : (
                <div className='flex h-full w-full items-center justify-center text-xl font-semibold text-muted-foreground'>{displayName.slice(0, 1).toUpperCase()}</div>
              )}
            </div>
            <div>
              <p className='text-sm text-muted-foreground'>Name</p>
              <p className='text-lg font-semibold'>{displayName}</p>
              <p className='text-sm text-muted-foreground'>@{user?.username}</p>
            </div>
          </div>
          <div className='flex min-w-0 flex-1 items-stretch gap-2 overflow-x-auto pb-1'>
            <div className='min-w-[130px] rounded-xl border border-border bg-muted/20 px-3 py-2'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Birth date</p>
              <p className='text-sm font-semibold'>{birthDate}</p>
            </div>
            <div className='min-w-[110px] rounded-xl border border-border bg-muted/20 px-3 py-2'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Primary sport</p>
              <p className='text-sm font-semibold'>{form.primary_sport || 'n/a'}</p>
            </div>
            <div className='min-w-[110px] rounded-xl border border-border bg-muted/20 px-3 py-2'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Height</p>
              <p className='text-sm font-semibold'>{form.height_cm ? `${form.height_cm} cm` : 'n/a'}</p>
            </div>
            <div className='min-w-[110px] rounded-xl border border-border bg-muted/20 px-3 py-2'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Weight</p>
              <p className='text-sm font-semibold'>{form.weight_kg ? `${form.weight_kg} kg` : 'n/a'}</p>
            </div>
            <div className='min-w-[220px] rounded-xl border border-border bg-muted/20 px-3 py-2'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Email</p>
              <p className='text-sm font-semibold'>{user?.email || 'n/a'}</p>
            </div>
          </div>
          <div className='flex items-center lg:ml-auto'>
            <div className={`rounded-xl border px-3 py-2 text-sm ${profileComplete ? 'border-emerald-400/50 text-emerald-300' : 'border-amber-400/50 text-amber-300'}`}>
              {profileComplete ? 'Profile ready' : 'Missing baseline fields'}
            </div>
          </div>
        </div>
      </Card>

      <Card className='p-6'>
        <p className='flex items-center gap-2 text-xl font-semibold'><Target className='h-5 w-5 text-cyan-300' />Personal Records</p>
        <p className='mt-1 text-sm text-muted-foreground'>Top 3 efforts by distance bucket, updated on each Strava detail sync.</p>
        {personalRecords.length ? (
          <div className='mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
            {personalRecords.map((group, idx) => (
              <div key={group.effort_key || idx} className='rounded-xl border border-border p-3'>
                <p className='text-base font-semibold'>{group.effort_label || 'Effort'}</p>
                <div className='mt-2 space-y-1 text-sm'>
                  {(group.records || []).slice(0, 3).map((record, i) => (
                    <div key={i} className='flex items-center justify-between gap-2 rounded-md bg-muted/20 px-2 py-1'>
                      <span className='text-muted-foreground'>#{record.rank || i + 1}</span>
                      <span className='font-semibold'>{Math.floor((Number(record.elapsed_time_s || 0)) / 60)}:{String(Number(record.elapsed_time_s || 0) % 60).padStart(2, '0')}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className='mt-4 rounded-xl border border-border p-3 text-sm text-muted-foreground'>No PR buckets yet. They will appear after detailed Strava syncs.</div>
        )}
      </Card>

      <Card className='p-6'>
        <p className='flex items-center gap-2 text-xl font-semibold'><Target className='h-5 w-5 text-cyan-300' />Training Preferences</p>
        <div className='mt-4 grid gap-4 md:grid-cols-2'>
          <label className='space-y-1'>
            <span className='text-sm text-muted-foreground'>Weekly target hours</span>
            <Input type='number' step='0.5' value={form.weekly_target_hours ?? ''} onChange={(e) => set('weekly_target_hours', Number(e.target.value || 0) || 0)} placeholder='6.5' />
          </label>
        </div>
        <div className='mt-4'>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save profile'}</Button>
        </div>
      </Card>

      <Card className='p-6'>
        <div className='flex items-center justify-between'>
          <p className='flex items-center gap-2 text-xl font-semibold'><HeartPulse className='h-5 w-5 text-cyan-300' />Heart Rate Zones</p>
          <div className='flex items-center gap-2'>
            <Button variant='outline' onClick={() => setEditZones((v) => !v)}>
              {editZones ? 'Cancel edit' : 'Edit'}
            </Button>
            {editZones && (
              <Button onClick={() => saveZones.mutate()} disabled={saveZones.isPending}>
                {saveZones.isPending ? 'Saving zones...' : 'Save zones'}
              </Button>
            )}
            <Button variant='outline' onClick={() => syncStravaProfile.mutate()} disabled={syncStravaProfile.isPending}>
              {syncStravaProfile.isPending ? 'Syncing...' : 'Sync from Strava'}
            </Button>
          </div>
        </div>
        <p className='mt-1 text-sm text-muted-foreground'>Source of truth: Strava athlete zones.</p>
        <div className='mt-4 grid gap-2 md:grid-cols-2'>
          {(editZones ? zoneDraft : (form.hr_zones || []).slice(0, 5)).length > 0 ? (
            (editZones ? zoneDraft : (form.hr_zones || []).slice(0, 5)).map((z: any, idx: number) => {
              const zmin = Number(z.min);
              const zmax = Number(z.max);
              const txt = zmax == null || zmax === -1 ? `${zmin}+ bpm` : `${zmin}-${zmax} bpm`;
              return (
                <div key={idx} className='relative overflow-hidden rounded-xl border border-border p-3 pl-5'>
                  <span className='absolute inset-y-0 left-0 w-1.5' style={{ backgroundColor: zoneColors[idx] || zoneColors[zoneColors.length - 1] }} />
                  <p className='text-sm text-muted-foreground'>Z{idx + 1}</p>
                  {editZones ? (
                    <div className='mt-2 grid grid-cols-2 gap-2'>
                      <label className='space-y-1'>
                        <span className='text-xs text-muted-foreground'>Min bpm</span>
                        <Input
                          type='number'
                          min={0}
                          value={zmin}
                          onChange={(e) =>
                            setZoneDraft((prev) =>
                              prev.map((item, i) => (i === idx ? { ...item, min: Number(e.target.value || 0) } : item))
                            )
                          }
                        />
                      </label>
                      <label className='space-y-1'>
                        <span className='text-xs text-muted-foreground'>Max bpm</span>
                        <Input
                          type='number'
                          min={-1}
                          value={zmax}
                          onChange={(e) =>
                            setZoneDraft((prev) =>
                              prev.map((item, i) => (i === idx ? { ...item, max: Number(e.target.value || -1) } : item))
                            )
                          }
                        />
                        {idx === 4 && <span className='text-[11px] text-muted-foreground'>Use -1 for open-ended Z5 max.</span>}
                      </label>
                    </div>
                  ) : (
                    <p className='text-lg font-semibold'>{txt}</p>
                  )}
                </div>
              );
            })
          ) : (
            <div className='rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-200'>
              No Strava HR zones in profile yet. Connect Strava and click Sync from Strava.
            </div>
          )}
        </div>
      </Card>

      <Card className='p-6'>
        <p className='flex items-center gap-2 text-xl font-semibold'><Bike className='h-5 w-5 text-cyan-300' />Gear</p>
        <p className='mt-1 text-sm text-muted-foreground'>Synced from Strava athlete and gear endpoints.</p>
        <div className='mt-4 grid gap-4 md:grid-cols-2'>
          <div className='space-y-2'>
            <p className='flex items-center gap-2 text-sm font-semibold text-muted-foreground'><Shoe className='h-4 w-4' />Shoes</p>
            {shoes.length ? (
              shoes.map((g, idx) => (
                <div key={g.id || idx} className='rounded-xl border border-border p-3'>
                  <p className='text-base font-semibold'>{g.name || `${g.brand_name || ''} ${g.model_name || ''}`.trim() || 'Shoe'}</p>
                  <p className='text-sm text-muted-foreground'>{km(g.distance)}{g.primary ? ' - Primary' : ''}</p>
                  {g.description ? <p className='mt-1 text-sm text-muted-foreground'>{g.description}</p> : null}
                </div>
              ))
            ) : (
              <div className='rounded-xl border border-border p-3 text-sm text-muted-foreground'>No shoes from Strava yet.</div>
            )}
          </div>
          <div className='space-y-2'>
            <p className='flex items-center gap-2 text-sm font-semibold text-muted-foreground'><Bike className='h-4 w-4' />Bikes</p>
            {bikes.length ? (
              bikes.map((g, idx) => (
                <div key={g.id || idx} className='rounded-xl border border-border p-3'>
                  <p className='text-base font-semibold'>{g.name || `${g.brand_name || ''} ${g.model_name || ''}`.trim() || 'Bike'}</p>
                  <p className='text-sm text-muted-foreground'>{km(g.distance)}{g.primary ? ' - Primary' : ''}</p>
                  {g.description ? <p className='mt-1 text-sm text-muted-foreground'>{g.description}</p> : null}
                </div>
              ))
            ) : (
              <div className='rounded-xl border border-border p-3 text-sm text-muted-foreground'>No bikes from Strava yet.</div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
