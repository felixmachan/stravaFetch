import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts';
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { LatLngBounds } from 'leaflet';
import { api } from '../lib/api';
import { formatDuration, formatPace, km, pacePerKm } from '../lib/analytics';
import { decodePolyline } from '../lib/polyline';
import { Bike, PersonStanding, Waves } from '../components/ui/icons';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { AiCallout } from '../components/ui/ai-callout';

function FitRouteBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length <= 1) return;
    const bounds = new LatLngBounds(points);
    const applyFit = () => {
      map.invalidateSize();
      map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
    };
    applyFit();
    const t1 = window.setTimeout(applyFit, 120);
    const t2 = window.setTimeout(applyFit, 420);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [map, points]);
  return null;
}

function kmMarkers(routePoints: [number, number][], distances: number[]) {
  if (!routePoints.length || !distances.length || routePoints.length !== distances.length) return [];
  const markers: Array<{ point: [number, number]; label: string }> = [];
  const maxKm = Math.floor((distances[distances.length - 1] || 0) / 1000);
  for (let k = 1; k <= maxKm; k += 1) {
    const targetM = k * 1000;
    const idx = distances.findIndex((d) => d >= targetM);
    if (idx > 0 && routePoints[idx]) {
      markers.push({ point: routePoints[idx], label: `${k} km` });
    }
  }
  return markers;
}

function formatClock(seconds = 0) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatPaceTick(secPerKm = 0) {
  if (!secPerKm) return 'n/a';
  const s = Math.max(0, Math.round(secPerKm));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, '0')}`;
}

function MetricTooltip({ active, payload, showHr = true, showAlt = true }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload || {};
  return (
    <div className='rounded-xl border border-slate-600/50 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl'>
      <p className='font-semibold text-slate-200'>{formatClock(point.t || 0)}</p>
      {showHr && point.hr != null && <p className='mt-1'>{'\u{1F493}'} <span className='font-semibold'>{Math.round(point.hr)} bpm</span></p>}
      {showAlt && point.alt != null && <p className='mt-1'>{'\u26F0\uFE0F'} <span className='font-semibold'>{Math.round(point.alt)} m</span></p>}
    </div>
  );
}

function ZoneTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const val = Number(payload[0]?.value || 0);
  const range = payload[0]?.payload?.range || 'Zone range n/a';
  return (
    <div className='rounded-xl border border-slate-600/50 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl'>
      <p className='font-semibold text-slate-200'>{label}</p>
      <p className='mt-1 text-slate-300'>{range}</p>
      <p className='mt-1'>Duration: <span className='font-semibold'>{formatDuration(val)}</span></p>
    </div>
  );
}

function PaceTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload || {};
  return (
    <div className='rounded-xl border border-slate-600/50 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl'>
      <p className='font-semibold text-slate-200'>{formatClock(Number(point.t || 0))}</p>
      <p className='text-slate-300'>{Number(point.x || 0).toFixed(2)} km</p>
      <p className='mt-1'>Pace: <span className='font-semibold'>{formatPace(Number(point.pace || 0))}</span></p>
    </div>
  );
}

function PowerTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload || {};
  return (
    <div className='rounded-xl border border-slate-600/50 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl'>
      <p className='font-semibold text-slate-200'>{formatClock(Number(point.t || 0))}</p>
      <p className='mt-1'>{'\u26A1'} <span className='font-semibold'>{Math.round(Number(point.watts || 0))} W</span></p>
    </div>
  );
}

function HrPaceTooltip({ active, payload, mode }: { active?: boolean; payload?: any[]; mode: 'pace' | 'hr' | 'combined' }) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload || {};
  const showHr = mode === 'hr' || mode === 'combined';
  const showPace = mode === 'pace' || mode === 'combined';
  return (
    <div className='rounded-xl border border-slate-600/50 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl'>
      <p className='font-semibold text-slate-200'>{formatClock(Number(point.t || 0))}</p>
      {showHr && point.hr != null ? <p className='mt-1'>{'\u{1F493}'} <span className='font-semibold'>{Math.round(Number(point.hr))} bpm</span></p> : null}
      {showPace && point.pace != null ? <p className='mt-1'>{'\u{1F3C3}'} <span className='font-semibold'>{formatPace(Number(point.pace || 0))}</span></p> : null}
    </div>
  );
}

function medalClass(rank: number) {
  if (rank === 1) return 'border-amber-200/80 bg-amber-300 text-amber-950';
  if (rank === 2) return 'border-slate-200/70 bg-slate-300 text-slate-900';
  return 'border-amber-200/70 bg-amber-700 text-amber-50';
}

function medalTooltipBorderClass(rank: number) {
  if (rank === 1) return 'border-amber-300/80';
  if (rank === 2) return 'border-slate-300/80';
  return 'border-amber-500/80';
}

function kudosAvatarUrl(k: any): string {
  return String(k?.avatar_url || k?.profile_medium || k?.profile || k?.avatar || k?.picture || '').trim();
}

function SportIcon({ type }: { type: string }) {
  const lower = (type || '').toLowerCase();
  if (lower.includes('run')) return <PersonStanding className='h-8 w-8 text-red-400' />;
  if (lower.includes('ride') || lower.includes('bike')) return <Bike className='h-8 w-8 text-sky-400' />;
  if (lower.includes('swim')) return <Waves className='h-8 w-8 text-cyan-300' />;
  return <PersonStanding className='h-8 w-8 text-zinc-400' />;
}

export function ActivityDetailPage() {
  const params = useParams();
  const id = params.id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [quickAi, setQuickAi] = useState('');
  const [hrPaceMode, setHrPaceMode] = useState<'pace' | 'hr' | 'combined'>('combined');

  const { data } = useQuery({ queryKey: ['activity', id], queryFn: async () => (await api.get(`/activities/${id}`)).data, enabled: Boolean(id) });
  const syncNow = useMutation({
    mutationFn: async () => (await api.post('/strava/sync-now')).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['activity', id] });
      qc.invalidateQueries({ queryKey: ['activities'] });
    },
  });
  const generateReaction = useMutation({
    mutationFn: async () => (await api.post(`/activities/${id}/regenerate-note`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['activity', id] });
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'AI reaction requested', message: 'It can be generated once per workout.' } }));
    },
    onError: (err: any) => {
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'AI reaction', message: err?.response?.data?.detail || 'Could not generate reaction.' } }));
      qc.invalidateQueries({ queryKey: ['activity', id] });
    },
  });

  const routePoints = useMemo<[number, number][]>(() => {
    if (!data) return [];
    if (Array.isArray(data?.streams?.latlng) && data.streams.latlng.length > 1) return data.streams.latlng;
    if (Array.isArray(data?.raw_payload?.map?.polyline_points) && data.raw_payload.map.polyline_points.length > 1) return data.raw_payload.map.polyline_points;
    if (data.map_summary_polyline) return decodePolyline(data.map_summary_polyline);
    return [];
  }, [data]);

  const chartData = useMemo(() => {
    const distance = data?.streams?.distance || [];
    const hr = data?.streams?.heartrate || [];
    const altitude = data?.streams?.altitude || [];
    const time = data?.streams?.time || [];
    const maxLen = Math.max(distance.length, hr.length, altitude.length, time.length);
    const moving = Number(data?.moving_time_s || 0);
    return Array.from({ length: maxLen }).map((_, i) => ({
      x: distance[i] ? Number((distance[i] / 1000).toFixed(2)) : Number(((time[i] || i * 10) / 60).toFixed(1)),
      t: time[i] ?? (maxLen > 1 ? Math.round((moving / (maxLen - 1)) * i) : 0),
      hr: hr[i] ?? null,
      alt: altitude[i] ?? null,
    }));
  }, [data]);
  const hasHrData = chartData.some((d) => d.hr != null);
  const hasAltData = chartData.some((d) => d.alt != null);
  const isSwim = String(data?.type || '').toLowerCase().includes('swim');
  const hrPaceSeries = useMemo(() => {
    const distance = (data?.streams?.distance || []) as number[];
    const time = (data?.streams?.time || []) as number[];
    const hr = (data?.streams?.heartrate || []) as number[];
    const len = Math.min(distance.length, time.length);
    if (len < 2) return [] as Array<{ t: number; hr: number | null; pace: number | null; pace_plot: number | null }>;
    const bucketSec = 10;
    const fallbackPace = pacePerKm(Number(data?.distance_m || 0), Number(data?.moving_time_s || 0)) || 360;
    let lastHr = hr.find((x) => x != null) ?? (data?.avg_hr ?? null);
    let emaPace = fallbackPace;
    const out: Array<{ t: number; hr: number | null; pace: number | null }> = [];
    let startIdx = 0;
    for (let i = 1; i < len; i += 1) {
      const elapsed = Number(time[i] || 0) - Number(time[startIdx] || 0);
      if (elapsed < bucketSec) continue;
      const dt = elapsed;
      const dd = Number(distance[i] || 0) - Number(distance[startIdx] || 0);
      let paceCandidate: number | null = null;
      if (dt > 0 && dd > 2) {
        const p = dt / (dd / 1000);
        if (Number.isFinite(p) && p >= 120 && p <= 1200) {
          const lower = emaPace * 0.55;
          const upper = emaPace * 1.6;
          paceCandidate = Math.max(lower, Math.min(upper, p));
        }
      }
      if (paceCandidate != null) emaPace = (emaPace * 0.82) + (paceCandidate * 0.18);
      let hrSum = 0;
      let hrCount = 0;
      for (let j = startIdx; j <= i; j += 1) {
        if (hr[j] != null) {
          hrSum += Number(hr[j]);
          hrCount += 1;
        }
      }
      const hrValue = hrCount > 0 ? (hrSum / hrCount) : (lastHr ?? null);
      if (hrValue != null) lastHr = hrValue;
      out.push({ t: Number(time[i] || 0), hr: hrValue, pace: Number(emaPace.toFixed(1)) });
      startIdx = i;
    }
    const paceValues = out.map((x) => Number(x.pace || 0)).filter((x) => Number.isFinite(x) && x > 0);
    if (!paceValues.length) {
      return out.map((x) => ({ ...x, pace_plot: null }));
    }
    const minP = Math.max(120, Math.floor(Math.min(...paceValues) - Math.max(8, (Math.max(...paceValues) - Math.min(...paceValues)) * 0.1)));
    const maxP = Math.min(1200, Math.ceil(Math.max(...paceValues) + Math.max(8, (Math.max(...paceValues) - Math.min(...paceValues)) * 0.1)));
    return out.map((x) => ({
      ...x,
      pace_plot: x.pace != null ? (maxP - Number(x.pace) + minP) : null,
    }));
  }, [data]);
  const hasPaceData = hrPaceSeries.some((x) => x.pace != null);
  const hrPaceDomain = useMemo<[number, number]>(() => {
    const p = hrPaceSeries.map((x) => Number(x.pace || 0)).filter((x) => Number.isFinite(x) && x > 0);
    if (!p.length) return [240, 480];
    const minP = Math.min(...p);
    const maxP = Math.max(...p);
    const pad = Math.max(8, (maxP - minP) * 0.1);
    return [Math.max(120, Math.floor(minP - pad)), Math.min(1200, Math.ceil(maxP + pad))];
  }, [hrPaceSeries]);
  const paceTickFromPlot = (v: number) => hrPaceDomain[1] - Number(v) + hrPaceDomain[0];
  const hasHrPaceCombinedData = hrPaceSeries.some((x) => x.hr != null || x.pace != null);

  const splits = useMemo(() => {
    const rawSplits = data?.raw_payload?.splits_metric || [];
    if (rawSplits.length) return rawSplits;
    const distances = data?.streams?.distance || [];
    const times = data?.streams?.time || [];
    if (!distances.length || !times.length || distances.length !== times.length) return [];
    const out: Array<{ split: number; distance: number; elapsed_time: number }> = [];
    const splitMeters = isSwim ? 100 : 1000;
    let splitIndex = 1;
    let prevTime = 0;
    for (let i = 0; i < distances.length; i += 1) {
      if (distances[i] >= splitIndex * splitMeters) {
        const t = Number(times[i] || 0);
        out.push({ split: splitIndex, distance: splitMeters, elapsed_time: t - prevTime });
        prevTime = t;
        splitIndex += 1;
      }
    }
    return out;
  }, [data, isSwim]);
  const distanceStream = data?.streams?.distance || [];
  const kmPins = useMemo(() => kmMarkers(routePoints, distanceStream), [routePoints, distanceStream]);
  const zoneRaw = data?.derived_metrics?.hr_zone_distribution || {};
  const movingTime = Number(data?.moving_time_s || 0);
  const hrRanges = data?.hr_zone_ranges || {};
  const zoneData = [
    { zone: 'Z1', range: hrRanges.Z1 || 'n/a', seconds: Math.round((movingTime * Number(zoneRaw.z1 || 0)) / 100), fill: '#34d399' },
    { zone: 'Z2', range: hrRanges.Z2 || 'n/a', seconds: Math.round((movingTime * Number(zoneRaw.z2 || 0)) / 100), fill: '#22d3ee' },
    { zone: 'Z3', range: hrRanges.Z3 || 'n/a', seconds: Math.round((movingTime * Number(zoneRaw.z3 || 0)) / 100), fill: '#facc15' },
    { zone: 'Z4', range: hrRanges.Z4 || 'n/a', seconds: Math.round((movingTime * Number(zoneRaw.z4 || 0)) / 100), fill: '#fb923c' },
    { zone: 'Z5', range: hrRanges.Z5 || 'n/a', seconds: Math.round((movingTime * Number(zoneRaw.z5 || 0)) / 100), fill: '#f43f5e' },
  ];
  const avg100m = Number(data?.distance_m || 0) > 0
    ? Number(data?.moving_time_s || 0) / (Number(data?.distance_m || 0) / 100)
    : 0;
  const cadence = data?.streams?.cadence || [];
  const avgCadence = cadence.length
    ? cadence.reduce((s: number, c: number) => s + c, 0) / cadence.length
    : (Number((data?.average_cadence ?? data?.raw_payload?.average_cadence) || 0) || null);
  const watts = data?.streams?.watts || [];
  const avgWatts = watts.length
    ? watts.reduce((sum: number, w: number) => sum + Number(w || 0), 0) / Math.max(1, watts.length)
    : (Number((data?.average_watts ?? data?.raw_payload?.average_watts) || 0) || null);
  const maxWatts = watts.length
    ? Math.max(...watts.map((w: number) => Number(w || 0)))
    : (Number((data?.max_watts ?? data?.raw_payload?.max_watts) || 0) || null);
  const powerSeries = useMemo(() => {
    const power = (data?.streams?.watts || []) as number[];
    const time = (data?.streams?.time || []) as number[];
    const len = Math.min(power.length, time.length);
    if (!len) return [] as Array<{ t: number; watts: number }>;
    return Array.from({ length: len }).map((_, i) => ({
      t: Number(time[i] || 0),
      watts: Number(power[i] || 0),
    }));
  }, [data]);
  const hasPowerData = powerSeries.some((x) => Number.isFinite(x.watts) && x.watts > 0);
  const bestEfforts = Array.isArray(data?.raw_payload?.best_efforts) ? data.raw_payload.best_efforts : [];
  const achievementCount = Number((data?.achievement_count ?? data?.raw_payload?.achievement_count) || 0);
  const newPrs = Array.isArray(data?.new_prs)
    ? data.new_prs
    : bestEfforts
        .filter((effort: any) => [1, 2, 3].includes(Number(effort?.pr_rank || 0)))
        .sort((a: any, b: any) => Number(a?.pr_rank || 0) - Number(b?.pr_rank || 0))
        .map((effort: any) => ({
          rank: Number(effort?.pr_rank || 0),
          effort_label: String(effort?.name || 'Effort'),
          elapsed_time_s: Number(effort?.elapsed_time || 0),
        }));
  const prMedals = useMemo(
    () => (newPrs || []).filter((item: any) => [1, 2, 3].includes(Number(item?.rank || 0))),
    [newPrs]
  );
  const kudosCount = Number((data?.kudos_count ?? data?.raw_payload?.kudos_count) || 0);
  const highlightedKudosers = Array.isArray(data?.raw_payload?.highlighted_kudosers) ? data.raw_payload.highlighted_kudosers : [];
  const fallbackKudosPreview = Array.isArray(data?.raw_payload?.kudos_preview) ? data.raw_payload.kudos_preview : [];
  const kudosPreview = useMemo(() => {
    const source = [...highlightedKudosers, ...fallbackKudosPreview];
    const byKey = new Map<string, any>();
    for (const item of source) {
      const label = String(item?.display_name || `${item?.firstname || ''} ${item?.lastname || ''}`.trim() || '').trim();
      const key = String(item?.id || label || '').trim();
      if (!key) continue;
      const prev = byKey.get(key);
      if (!prev) {
        byKey.set(key, item);
        continue;
      }
      const prevHasImg = Boolean(kudosAvatarUrl(prev));
      const nextHasImg = Boolean(kudosAvatarUrl(item));
      if (!prevHasImg && nextHasImg) byKey.set(key, item);
    }
    return Array.from(byKey.values()).slice(0, 8);
  }, [highlightedKudosers, fallbackKudosPreview]);
  useEffect(() => {
    if (data?.activity_reaction?.text_summary) {
      setQuickAi(data.activity_reaction.text_summary);
    } else {
      setQuickAi('');
    }
  }, [data?.activity_reaction?.text_summary]);

  if (!data) return null;

  return (
    <div className='space-y-5'>
      <Card className='p-6'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <div className='flex items-center gap-3'>
            <div className='grid h-12 w-12 place-items-center rounded-xl border border-border bg-background/60'>
              <SportIcon type={data.type} />
            </div>
            <div>
              <p className='text-3xl font-semibold'>{data.name}</p>
              <p className='text-base text-muted-foreground'>{new Date(data.start_date).toLocaleString()}</p>
            </div>
          </div>
          <Button variant='outline' onClick={() => navigate('/activities')}>Back</Button>
        </div>
        <div className='mt-6 grid grid-cols-2 gap-4 md:grid-cols-4'>
          <div><p className='text-sm text-muted-foreground'>Distance</p><p className='text-3xl font-semibold'>{km(data.distance_m).toFixed(2)} km</p></div>
          <div><p className='text-sm text-muted-foreground'>Time</p><p className='text-3xl font-semibold'>{formatDuration(data.moving_time_s)}</p></div>
          <div><p className='text-sm text-muted-foreground'>Avg pace</p><p className='text-3xl font-semibold'>{formatPace(pacePerKm(data.distance_m, data.moving_time_s))}</p></div>
          <div><p className='text-sm text-muted-foreground'>Avg HR</p><p className='text-3xl font-semibold'>{data.avg_hr ? Math.round(data.avg_hr) : 'n/a'}</p></div>
          <div><p className='text-sm text-muted-foreground'>Avg Power</p><p className='text-3xl font-semibold'>{avgWatts ? `${Math.round(avgWatts)} W` : 'n/a'}</p></div>
          <div><p className='text-sm text-muted-foreground'>Max Power</p><p className='text-3xl font-semibold'>{maxWatts ? `${Math.round(maxWatts)} W` : 'n/a'}</p></div>
          <div><p className='text-sm text-muted-foreground'>Achievements (Strava)</p><p className='text-3xl font-semibold'>{achievementCount}</p></div>
        </div>
        <div className='mt-5 flex items-center justify-between gap-4 text-sm text-muted-foreground'>
          <div className='flex min-w-0 flex-wrap items-center gap-3'>
            <span className='font-medium'>Kudos: {kudosCount}</span>
            {kudosPreview.slice(0, 6).map((k: any, idx: number) => {
              const img = kudosAvatarUrl(k);
              const label =
                k?.display_name
                || `${k?.firstname || ''} ${k?.lastname || ''}`.trim()
                || `Athlete ${idx + 1}`;
              return (
                <div key={`${k?.id || idx}`} className='flex items-center gap-1 rounded-full border border-border px-2 py-1'>
                  {img ? (
                    <img src={img} alt={label} className='h-5 w-5 rounded-full object-cover' />
                  ) : (
                    <div className='grid h-5 w-5 place-items-center rounded-full bg-muted text-[10px] text-foreground'>
                      {label.slice(0, 1).toUpperCase()}
                    </div>
                  )}
                  <span className='text-xs'>{label}</span>
                </div>
              );
            })}
          </div>
          {prMedals.length > 0 ? (
            <div className='flex shrink-0 items-center gap-2'>
              {prMedals.map((pr: any, idx: number) => (
                <div key={`${pr?.rank || 0}-${idx}`} className='group relative'>
                  <div className='relative h-9 w-8'>
                    <span className={`absolute left-1 top-0 h-2 w-2 rounded-sm border ${medalClass(Number(pr?.rank || 3))}`} />
                    <span className={`absolute right-1 top-0 h-2 w-2 rounded-sm border ${medalClass(Number(pr?.rank || 3))}`} />
                    <span className={`absolute bottom-0 left-0 grid h-7 w-8 place-items-center rounded-full border text-[10px] font-bold shadow-md ${medalClass(Number(pr?.rank || 3))}`}>
                      {Number(pr?.rank || 0) === 1 ? 'PR' : `${Number(pr?.rank || 0)}`}
                    </span>
                  </div>
                  <div className={`pointer-events-none absolute -top-2 right-0 z-30 w-60 -translate-y-full rounded-lg border bg-slate-950/95 px-3 py-2 text-xs text-slate-100 opacity-0 shadow-2xl transition-opacity duration-150 group-hover:opacity-100 ${medalTooltipBorderClass(Number(pr?.rank || 3))}`}>
                    <p>New Personal Record at {String(pr?.effort_label || 'Effort')}!</p>
                    <p>Congratulations!</p>
                    <p>Time: {formatDuration(Number(pr?.elapsed_time_s || 0))}</p>
                    <span className={`absolute -bottom-1 right-4 h-2 w-2 rotate-45 border-b border-r bg-slate-950/95 ${medalTooltipBorderClass(Number(pr?.rank || 3))}`} />
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        {!data?.fully_synced && (
          <p className='mt-4 text-sm text-amber-300'>
            Detailed sync in progress{data?.sync_error ? ` (${data.sync_error})` : ''}.
          </p>
        )}
      </Card>

      <div>
        {quickAi ? (
          <AiCallout title='AI Coach Note'>
            {quickAi}
          </AiCallout>
        ) : (
          <div className='space-y-2 rounded-xl border border-border bg-muted/20 px-3 py-3 text-sm text-muted-foreground'>
            <p>No AI reaction generated for this workout yet.</p>
            <Button variant='outline' onClick={() => generateReaction.mutate()} disabled={generateReaction.isPending}>
              {generateReaction.isPending ? 'Generating...' : 'Generate AI reaction (one-time)'}
            </Button>
          </div>
        )}
      </div>

      {!isSwim && (
        <Card className='h-[420px] overflow-hidden p-3'>
          {routePoints.length > 1 ? (
            <MapContainer center={routePoints[0]} zoom={12} style={{ height: '100%' }}>
              <TileLayer url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' />
              <FitRouteBounds points={routePoints} />
              <Polyline positions={routePoints} pathOptions={{ color: '#ef4444', weight: 5, opacity: 0.95 }} />
              <CircleMarker center={routePoints[0]} radius={7} pathOptions={{ color: '#22c55e', fillColor: '#22c55e', fillOpacity: 1 }}>
                <Tooltip permanent direction='top' offset={[0, -8]}>Start</Tooltip>
              </CircleMarker>
              <CircleMarker center={routePoints[routePoints.length - 1]} radius={7} pathOptions={{ color: '#ef4444', fillColor: '#ef4444', fillOpacity: 1 }}>
                <Tooltip permanent direction='top' offset={[0, -8]}>Finish</Tooltip>
              </CircleMarker>
              {kmPins.map((pin, idx) => (
                <CircleMarker key={idx} center={pin.point} radius={4} pathOptions={{ color: '#f97316', fillColor: '#f97316', fillOpacity: 0.9 }}>
                  <Tooltip>{pin.label}</Tooltip>
                </CircleMarker>
              ))}
            </MapContainer>
          ) : (
            <div className='grid h-full place-items-center text-sm text-muted-foreground'>No route data available for this activity.</div>
          )}
        </Card>
      )}
      {(!hasHrData || (!isSwim && (!hasAltData || !hasPaceData)) || splits.length === 0) && (
        <Card className='p-4'>
          <p className='text-sm text-muted-foreground'>Some stream data is still missing for this activity.</p>
          <Button className='mt-2' variant='outline' onClick={() => syncNow.mutate()} disabled={syncNow.isPending}>
            {syncNow.isPending ? 'Syncing...' : 'Sync streams now'}
          </Button>
        </Card>
      )}

      {isSwim ? (
        <div className='grid gap-4 md:grid-cols-2'>
          <Card className='h-72 p-4'>
            <p className='text-base font-semibold'>Heart Rate</p>
            <div className='mt-3 h-[220px] rounded-xl'>
              {hasHrData ? (
                <ResponsiveContainer width='100%' height='100%'>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id='hrGradient' x1='0' y1='0' x2='0' y2='1'>
                        <stop offset='0%' stopColor='#fb7185' stopOpacity={0.65} />
                        <stop offset='100%' stopColor='#fb7185' stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray='4 4' stroke='hsl(var(--border))' />
                    <XAxis dataKey='t' tickFormatter={(v) => formatClock(Number(v))} minTickGap={28} />
                    <YAxis />
                    <ChartTooltip content={<MetricTooltip showHr showAlt={false} />} />
                    <Area type='monotone' dataKey='hr' stroke='#fb7185' fill='url(#hrGradient)' strokeWidth={2.2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className='grid h-full place-items-center text-sm text-muted-foreground'>No heart-rate stream yet.</div>
              )}
            </div>
          </Card>
          <Card className='h-72 p-4'>
            <p className='text-base font-semibold'><Waves className='mr-1 inline h-4 w-4 text-cyan-300' />Swim Metrics</p>
            <div className='mt-4 grid grid-cols-2 gap-4'>
              <div className='rounded-xl border border-border p-3'>
                <p className='text-xs text-muted-foreground'>Average 100m</p>
                <p className='text-2xl font-semibold'>{formatClock(avg100m)} /100m</p>
              </div>
              <div className='rounded-xl border border-border p-3'>
                <p className='text-xs text-muted-foreground'>Avg stroke cadence</p>
                <p className='text-2xl font-semibold'>{avgCadence ? `${Math.round(avgCadence)} spm` : 'n/a'}</p>
              </div>
            </div>
          </Card>
        </div>
      ) : (
        <>
          <div className='grid gap-4 md:grid-cols-2'>
            <Card className='h-72 p-4'>
              <p className='text-base font-semibold'>Power</p>
              <div className='mt-3 h-[220px] rounded-xl'>
                {hasPowerData ? (
                  <ResponsiveContainer width='100%' height='100%'>
                    <AreaChart data={powerSeries}>
                      <defs>
                        <linearGradient id='powerGradient' x1='0' y1='0' x2='0' y2='1'>
                          <stop offset='0%' stopColor='#a3e635' stopOpacity={0.45} />
                          <stop offset='100%' stopColor='#a3e635' stopOpacity={0.06} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray='4 4' stroke='hsl(var(--border))' />
                      <XAxis dataKey='t' tickFormatter={(v) => formatClock(Number(v))} minTickGap={28} />
                      <YAxis />
                      <ChartTooltip content={<PowerTooltip />} />
                      <Area type='monotone' dataKey='watts' stroke='#a3e635' dot={false} strokeWidth={2.2} fill='url(#powerGradient)' />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className='grid h-full place-items-center text-sm text-muted-foreground'>No power stream yet.</div>
                )}
              </div>
            </Card>
            <Card className='h-72 p-4'>
              <p className='text-base font-semibold'>Elevation</p>
              <div className='mt-3 h-[220px] rounded-xl'>
                {hasAltData ? (
                  <ResponsiveContainer width='100%' height='100%'>
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id='altGradient' x1='0' y1='0' x2='0' y2='1'>
                          <stop offset='0%' stopColor='#38bdf8' stopOpacity={0.45} />
                          <stop offset='100%' stopColor='#38bdf8' stopOpacity={0.04} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray='4 4' stroke='hsl(var(--border))' />
                      <XAxis dataKey='t' tickFormatter={(v) => formatClock(Number(v))} minTickGap={28} />
                      <YAxis />
                      <ChartTooltip content={<MetricTooltip showHr={false} showAlt />} />
                      <Area type='monotone' dataKey='alt' stroke='#38bdf8' dot={false} strokeWidth={2.4} fill='url(#altGradient)' />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className='grid h-full place-items-center text-sm text-muted-foreground'>No elevation stream yet.</div>
                )}
              </div>
            </Card>
          </div>

          <Card className='h-72 p-4'>
            <div className='mb-2 flex items-center justify-between gap-3'>
              <p className='text-base font-semibold'>Heart Rate & Pace</p>
              <select
                className='h-9 rounded-lg border border-border bg-background px-2 text-sm'
                value={hrPaceMode}
                onChange={(e) => setHrPaceMode((e.target.value as 'pace' | 'hr' | 'combined'))}
              >
                <option value='pace'>Pace</option>
                <option value='hr'>HR</option>
                <option value='combined'>Combined</option>
              </select>
            </div>
            <div className='mt-3 h-[220px] rounded-xl'>
              {hasHrPaceCombinedData ? (
                <ResponsiveContainer width='100%' height='100%'>
                  <AreaChart data={hrPaceSeries}>
                    <defs>
                      <linearGradient id='hrCombinedGradient' x1='0' y1='0' x2='0' y2='1'>
                        <stop offset='0%' stopColor='#fb7185' stopOpacity={0.55} />
                        <stop offset='100%' stopColor='#fb7185' stopOpacity={0.04} />
                      </linearGradient>
                      <linearGradient id='paceCombinedGradient' x1='0' y1='0' x2='0' y2='1'>
                        <stop offset='0%' stopColor='#22d3ee' stopOpacity={0.45} />
                        <stop offset='100%' stopColor='#22d3ee' stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray='4 4' stroke='hsl(var(--border))' />
                    <XAxis dataKey='t' tickFormatter={(v) => formatClock(Number(v))} minTickGap={28} />
                    {(hrPaceMode === 'hr' || hrPaceMode === 'combined') && <YAxis yAxisId='hr' orientation='left' />}
                    {(hrPaceMode === 'pace' || hrPaceMode === 'combined') && (
                      <YAxis yAxisId='pace' orientation='right' domain={hrPaceDomain} tickFormatter={(v) => formatPaceTick(paceTickFromPlot(Number(v)))} />
                    )}
                    <ChartTooltip content={<HrPaceTooltip mode={hrPaceMode} />} />
                    {(hrPaceMode === 'hr' || hrPaceMode === 'combined') && (
                      <Area yAxisId='hr' type='monotone' dataKey='hr' stroke='#fb7185' dot={false} strokeWidth={2.1} fill='url(#hrCombinedGradient)' connectNulls />
                    )}
                    {(hrPaceMode === 'pace' || hrPaceMode === 'combined') && (
                      <Area yAxisId='pace' type='monotone' dataKey='pace_plot' stroke='#22d3ee' dot={false} strokeWidth={2.1} fill='url(#paceCombinedGradient)' connectNulls />
                    )}
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className='grid h-full place-items-center text-sm text-muted-foreground'>No HR/Pace stream yet.</div>
              )}
            </div>
          </Card>
        </>
      )}

      <div className='grid gap-4 md:grid-cols-2'>
        <Card className='p-4'>
          <div className='flex items-center justify-between'>
            <p className='text-base font-semibold'>Best Efforts</p>
            <Badge>{bestEfforts.length}</Badge>
          </div>
          {bestEfforts.length ? (
            <div className='mt-3 max-h-64 overflow-y-auto'>
              <table className='w-full text-sm'>
                <thead className='text-muted-foreground'>
                  <tr>
                    <th className='py-1 text-left'>Name</th>
                    <th className='py-1 text-left'>PR rank</th>
                    <th className='py-1 text-left'>Elapsed</th>
                  </tr>
                </thead>
                <tbody>
                  {bestEfforts.slice(0, 12).map((effort: any, idx: number) => (
                    <tr key={`${effort?.id || idx}`} className='border-t border-border'>
                      <td className='py-1'>{String(effort?.name || effort?.activity?.name || `Effort ${idx + 1}`)}</td>
                      <td className='py-1'>{effort?.pr_rank ? `#${effort.pr_rank}` : 'n/a'}</td>
                      <td className='py-1'>{formatDuration(Number(effort?.elapsed_time || 0))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className='mt-3 text-sm text-muted-foreground'>No best-effort data available for this activity.</div>
          )}
        </Card>
        <Card className='p-4'>
          <div className='flex items-center justify-between'>
            <p className='text-base font-semibold'>Splits</p>
            <Badge>{splits.length} splits</Badge>
          </div>
          <div className='mt-3 max-h-64 overflow-y-auto'>
            <table className='w-full text-sm'>
              <thead className='text-muted-foreground'><tr><th className='py-1 text-left'>#</th><th className='py-1 text-left'>Distance</th><th className='py-1 text-left'>Time</th></tr></thead>
              <tbody>
                {splits.map((s: any, i: number) => (
                  <tr key={i} className='border-t border-border'><td className='py-1'>{s.split || i + 1}</td><td className='py-1'>{isSwim ? `${Math.round(s.distance || 0)} m` : `${((s.distance || 0) / 1000).toFixed(2)} km`}</td><td className='py-1'>{formatDuration(s.elapsed_time || 0)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className='p-4'>
          <p className='mb-2 text-base font-semibold'>Heart Rate Zones</p>
          <div className='h-44'>
            <ResponsiveContainer width='100%' height='100%'>
              <BarChart data={zoneData} layout='vertical' margin={{ top: 6, right: 20, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray='3 3' stroke='hsl(var(--border))' />
                <XAxis type='number' tickFormatter={(v) => formatDuration(Number(v))} />
                <YAxis dataKey='zone' type='category' width={36} />
                <ChartTooltip content={<ZoneTooltip />} />
                <Bar dataKey='seconds' radius={[0, 8, 8, 0]}>
                  {zoneData.map((z) => (
                    <Cell key={z.zone} fill={z.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}

