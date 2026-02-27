import { Waves } from '../components/ui/icons';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts';
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { LatLngBounds } from 'leaflet';
import { api } from '../lib/api';
import { formatDuration, formatPace, km, pacePerKm } from '../lib/analytics';
import { decodePolyline } from '../lib/polyline';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';

function FitRouteBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  if (points.length > 1) {
    const bounds = new LatLngBounds(points);
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
  }
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

function MetricTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload || {};
  return (
    <div className='rounded-xl border border-slate-600/50 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl'>
      <p className='font-semibold text-slate-200'>{formatClock(point.t || 0)}</p>
      {point.hr != null && <p className='mt-1'>❤️ {Math.round(point.hr)} bpm</p>}
      {point.alt != null && <p>⛰ {Math.round(point.alt)} m</p>}
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

export function ActivityDetailPage() {
  const params = useParams();
  const id = params.id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [quickAi, setQuickAi] = useState('');

  const { data } = useQuery({ queryKey: ['activity', id], queryFn: async () => (await api.get(`/activities/${id}`)).data, enabled: Boolean(id) });
  const syncNow = useMutation({
    mutationFn: async () => (await api.post('/strava/sync-now')).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['activity', id] });
      qc.invalidateQueries({ queryKey: ['activities'] });
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
  const avgCadence = cadence.length ? cadence.reduce((s: number, c: number) => s + c, 0) / cadence.length : null;
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
          <div>
            <p className='text-3xl font-semibold'>{data.name}</p>
            <p className='text-base text-muted-foreground'>{new Date(data.start_date).toLocaleString()}</p>
          </div>
          <div className='flex items-center gap-2'>
            <Badge className='text-sm'>{data.type}</Badge>
            <Button variant='outline' onClick={() => navigate('/activities')}>Back</Button>
          </div>
        </div>
        <div className='mt-6 grid grid-cols-2 gap-4 md:grid-cols-4'>
          <div><p className='text-sm text-muted-foreground'>Distance</p><p className='text-3xl font-semibold'>{km(data.distance_m).toFixed(2)} km</p></div>
          <div><p className='text-sm text-muted-foreground'>Time</p><p className='text-3xl font-semibold'>{formatDuration(data.moving_time_s)}</p></div>
          <div><p className='text-sm text-muted-foreground'>Avg pace</p><p className='text-3xl font-semibold'>{formatPace(pacePerKm(data.distance_m, data.moving_time_s))}</p></div>
          <div><p className='text-sm text-muted-foreground'>Avg HR</p><p className='text-3xl font-semibold'>{data.avg_hr ? Math.round(data.avg_hr) : 'n/a'}</p></div>
        </div>
      </Card>

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
      {(!hasHrData || (!isSwim && !hasAltData) || splits.length === 0) && (
        <Card className='p-4'>
          <p className='text-sm text-muted-foreground'>Some stream data is still missing for this activity.</p>
          <Button className='mt-2' variant='outline' onClick={() => syncNow.mutate()} disabled={syncNow.isPending}>
            {syncNow.isPending ? 'Syncing...' : 'Sync streams now'}
          </Button>
        </Card>
      )}

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
                  <XAxis dataKey='x' />
                  <YAxis />
                  <ChartTooltip content={<MetricTooltip />} />
                  <Area type='monotone' dataKey='hr' stroke='#fb7185' fill='url(#hrGradient)' strokeWidth={2.2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className='grid h-full place-items-center text-sm text-muted-foreground'>No heart-rate stream yet.</div>
            )}
          </div>
        </Card>
        {isSwim ? (
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
        ) : (
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
                    <XAxis dataKey='x' />
                    <YAxis />
                    <ChartTooltip content={<MetricTooltip />} />
                    <Area type='monotone' dataKey='alt' stroke='#38bdf8' dot={false} strokeWidth={2.4} fill='url(#altGradient)' />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className='grid h-full place-items-center text-sm text-muted-foreground'>No elevation stream yet.</div>
              )}
            </div>
          </Card>
        )}
      </div>

      <div className='grid gap-4 md:grid-cols-2'>
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

        <Card className='p-4'>
          <p className='text-base font-semibold'>AI Coach Note</p>
          {quickAi ? <p className='mt-2 rounded-xl border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100'>{quickAi}</p> : null}
          {!quickAi ? <p className='mt-2 rounded-xl border border-border bg-muted/20 px-3 py-2 text-sm text-muted-foreground'>Reaction is being generated automatically after sync...</p> : null}
        </Card>
      </div>
    </div>
  );
}
