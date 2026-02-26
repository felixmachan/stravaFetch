import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer } from 'recharts';
import { MapContainer, Polyline, TileLayer } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import './styles.css';

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api', withCredentials: true });
const qc = new QueryClient();

function Dashboard() {
  const { data } = useQuery({ queryKey: ['activities'], queryFn: async () => (await api.get('/activities')).data });
  const latest = data?.[0];
  const trend = (data || []).slice(0, 14).map((a: any, i: number) => ({ i, km: (a.distance_m || 0) / 1000 }));
  return <div className='p-4 space-y-4'><h1 className='text-2xl font-bold'>PacePilot</h1><div className='card'><h2>Last activity</h2><p>{latest?.name || 'No activity yet'}</p><p>{latest ? `${(latest.distance_m/1000).toFixed(2)}km` : ''}</p></div><div className='card h-48'><ResponsiveContainer width='100%' height='100%'><LineChart data={trend}><XAxis dataKey='i'/><YAxis/><Line dataKey='km' stroke='#22d3ee'/></LineChart></ResponsiveContainer></div></div>;
}

function Activities() {
  const { data } = useQuery({ queryKey: ['activities'], queryFn: async () => (await api.get('/activities')).data });
  return <div className='p-4'><h1 className='text-xl'>Activities</h1>{(data||[]).map((a:any)=><Link className='block card my-2' key={a.id} to={`/activities/${a.id}`}>{a.name} - {a.type}</Link>)}</div>;
}

function ActivityDetail() {
  const id = window.location.pathname.split('/').pop();
  const { data } = useQuery({ queryKey: ['activity', id], queryFn: async () => (await api.get(`/activities/${id}`)).data });
  const pts = data?.raw_payload?.map?.polyline_points || [];
  return <div className='p-4 space-y-4'><h1>{data?.name}</h1><div className='h-64'>{Array.isArray(pts) ? <MapContainer center={[47.49,19.04]} zoom={11} style={{height:'100%'}}><TileLayer url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' />{pts.length>1 && <Polyline positions={pts}/>}</MapContainer> : <div className='card'>No map data</div>}</div><div className='card'>{data?.coach_note?.text_summary || 'No coach note yet'}</div></div>;
}

function Login() {
  const onLogin = async () => { await api.post('/auth/login', { username: 'admin@local', password: 'admin' }); location.href = '/'; };
  return <div className='p-4'><button className='btn' onClick={onLogin}>Login as admin</button><a className='btn ml-2' href='http://localhost:8000/api/auth/strava/connect'>Connect Strava</a></div>;
}

function App(){return <BrowserRouter><nav className='p-4 space-x-4'><Link to='/'>Dashboard</Link><Link to='/activities'>Activities</Link><Link to='/login'>Login</Link></nav><Routes><Route path='/' element={<Dashboard/>}/><Route path='/activities' element={<Activities/>}/><Route path='/activities/:id' element={<ActivityDetail/>}/><Route path='/login' element={<Login/>}/></Routes></BrowserRouter>}

ReactDOM.createRoot(document.getElementById('root')!).render(<QueryClientProvider client={qc}><App/></QueryClientProvider>);
