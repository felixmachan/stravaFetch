import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
    const trend = (data || []).slice(0, 14).map((a, i) => ({ i, km: (a.distance_m || 0) / 1000 }));
    return _jsxs("div", { className: 'p-4 space-y-4', children: [_jsx("h1", { className: 'text-2xl font-bold', children: "PacePilot" }), _jsxs("div", { className: 'card', children: [_jsx("h2", { children: "Last activity" }), _jsx("p", { children: latest?.name || 'No activity yet' }), _jsx("p", { children: latest ? `${(latest.distance_m / 1000).toFixed(2)}km` : '' })] }), _jsx("div", { className: 'card h-48', children: _jsx(ResponsiveContainer, { width: '100%', height: '100%', children: _jsxs(LineChart, { data: trend, children: [_jsx(XAxis, { dataKey: 'i' }), _jsx(YAxis, {}), _jsx(Line, { dataKey: 'km', stroke: '#22d3ee' })] }) }) })] });
}
function Activities() {
    const { data } = useQuery({ queryKey: ['activities'], queryFn: async () => (await api.get('/activities')).data });
    return _jsxs("div", { className: 'p-4', children: [_jsx("h1", { className: 'text-xl', children: "Activities" }), (data || []).map((a) => _jsxs(Link, { className: 'block card my-2', to: `/activities/${a.id}`, children: [a.name, " - ", a.type] }, a.id))] });
}
function ActivityDetail() {
    const id = window.location.pathname.split('/').pop();
    const { data } = useQuery({ queryKey: ['activity', id], queryFn: async () => (await api.get(`/activities/${id}`)).data });
    const pts = data?.raw_payload?.map?.polyline_points || [];
    return _jsxs("div", { className: 'p-4 space-y-4', children: [_jsx("h1", { children: data?.name }), _jsx("div", { className: 'h-64', children: Array.isArray(pts) ? _jsxs(MapContainer, { center: [47.49, 19.04], zoom: 11, style: { height: '100%' }, children: [_jsx(TileLayer, { url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' }), pts.length > 1 && _jsx(Polyline, { positions: pts })] }) : _jsx("div", { className: 'card', children: "No map data" }) }), _jsx("div", { className: 'card', children: data?.coach_note?.text_summary || 'No coach note yet' })] });
}
function Login() {
    const onLogin = async () => { await api.post('/auth/login', { username: 'admin@local', password: 'admin' }); location.href = '/'; };
    return _jsxs("div", { className: 'p-4', children: [_jsx("button", { className: 'btn', onClick: onLogin, children: "Login as admin" }), _jsx("a", { className: 'btn ml-2', href: 'http://localhost:8000/api/auth/strava/connect', children: "Connect Strava" })] });
}
function App() { return _jsxs(BrowserRouter, { children: [_jsxs("nav", { className: 'p-4 space-x-4', children: [_jsx(Link, { to: '/', children: "Dashboard" }), _jsx(Link, { to: '/activities', children: "Activities" }), _jsx(Link, { to: '/login', children: "Login" })] }), _jsxs(Routes, { children: [_jsx(Route, { path: '/', element: _jsx(Dashboard, {}) }), _jsx(Route, { path: '/activities', element: _jsx(Activities, {}) }), _jsx(Route, { path: '/activities/:id', element: _jsx(ActivityDetail, {}) }), _jsx(Route, { path: '/login', element: _jsx(Login, {}) })] })] }); }
ReactDOM.createRoot(document.getElementById('root')).render(_jsx(QueryClientProvider, { client: qc, children: _jsx(App, {}) }));
