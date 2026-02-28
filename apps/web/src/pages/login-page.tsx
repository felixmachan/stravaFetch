import { useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Bike, Calendar, PersonStanding, Target, Waves } from '../components/ui/icons';
import { useAuth } from '../context/auth-context';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { api } from '../lib/api';

type Mode = 'login' | 'register';

type StravaPrefill = {
  display_name?: string;
  username_suggestion?: string;
  primary_sport?: string;
  weight_kg?: number;
  profile_medium?: string;
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

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function datePlusDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return toIsoDate(d);
}

function buildInitialRegisterForm() {
  const prefillEnabled = import.meta.env.DEV && String(import.meta.env.VITE_PREFILL_REGISTRATION ?? '1') !== '0';
  if (!prefillEnabled) {
    return {
      username: '',
      email: '',
      password: '',
      display_name: '',
      primary_sport: '',
      birth_date: '',
      height_cm: '',
      weight_kg: '',
      goals: '',
      goal_type: 'race',
      goal_event_name: '',
      goal_event_date: '',
      goal_distance_km: '',
      has_time_goal_for_race: false,
      goal_target_time_min: '',
      annual_km_goal: '',
      ai_memory_days: '30',
      training_days: ['mon', 'wed', 'fri'] as string[],
      strava_signup_token: '',
    };
  }
  return {
    username: 'felix_machan',
    email: 'felix.machan@gmail.com',
    password: 'test123456',
    display_name: 'Felix',
    primary_sport: 'Run',
    birth_date: '2002-08-07',
    height_cm: '188',
    weight_kg: '77',
    goals: 'Sub-1:45 half marathon while keeping recovery safe.',
    goal_type: 'race',
    goal_event_name: 'Vivicitta Felmaraton Budapest',
    goal_event_date: datePlusDays(30),
    goal_distance_km: '21.1',
    has_time_goal_for_race: false,
    goal_target_time_min: '',
    annual_km_goal: '',
    ai_memory_days: '10',
    training_days: ['tue', 'thu', 'fri', 'sun'] as string[],
    strava_signup_token: '',
  };
}

export function LoginPage() {
  const { isAuthenticated, login, register, loginAsAdmin, loading } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [mode, setMode] = useState<Mode>('login');
  const [busy, setBusy] = useState(false);
  const [stravaBusy, setStravaBusy] = useState(false);
  const [registerProgress, setRegisterProgress] = useState(0);
  const [onboardingGate, setOnboardingGate] = useState(false);
  const [registerBackendMessage, setRegisterBackendMessage] = useState('');
  const [registerBackendDetails, setRegisterBackendDetails] = useState<string[]>([]);
  const [registerHintText, setRegisterHintText] = useState('');
  const [error, setError] = useState('');
  const [stravaLinkedForSignup, setStravaLinkedForSignup] = useState(false);
  const [stravaAvatar, setStravaAvatar] = useState('');

  const [loginForm, setLoginForm] = useState({ usernameOrEmail: '', password: '' });
  const [registerForm, setRegisterForm] = useState(buildInitialRegisterForm);

  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  useEffect(() => {
    const requestedMode = (searchParams.get('mode') || '').toLowerCase();
    if (requestedMode === 'register') setMode('register');
  }, [searchParams]);

  useEffect(() => {
    const token = searchParams.get('token');
    const strava = searchParams.get('strava');
    if (!token || strava !== 'prefill') return;

    let mounted = true;
    setMode('register');
    setStravaBusy(true);
    api
      .get('/auth/strava/signup-prefill', { params: { token }, suppressToast: true } as any)
      .then((res) => {
        if (!mounted) return;
        const prefill = (res.data?.prefill || {}) as StravaPrefill;
        setRegisterForm((prev) => ({
          ...prev,
          strava_signup_token: res.data?.strava_signup_token || token,
          username: prev.username || prefill.username_suggestion || '',
          display_name: prev.display_name || prefill.display_name || '',
          primary_sport: prev.primary_sport || prefill.primary_sport || 'Run',
          weight_kg: prev.weight_kg || (prefill.weight_kg ? String(prefill.weight_kg) : ''),
        }));
        setStravaAvatar(prefill.profile_medium || '');
        setStravaLinkedForSignup(true);
        setError('');
        setSearchParams({ mode: 'register' });
      })
      .catch(() => {
        if (!mounted) return;
        setError('Strava prefill link expired. Connect Strava again.');
      })
      .finally(() => {
        if (mounted) setStravaBusy(false);
      });

    return () => {
      mounted = false;
    };
  }, [searchParams, setSearchParams]);

  const registerReady = useMemo(() => {
    const base = Boolean(registerForm.username && registerForm.email && registerForm.password && registerForm.primary_sport && registerForm.goal_type);
    if (!base) return false;
    if ((registerForm.training_days || []).length === 0) return false;
    if (registerForm.goal_type === 'race') return Boolean(registerForm.goal_event_name && registerForm.goal_event_date && registerForm.goal_distance_km);
    if (registerForm.goal_type === 'time_trial') return Boolean(registerForm.goal_distance_km && registerForm.goal_target_time_min);
    if (registerForm.goal_type === 'annual_km') return Boolean(registerForm.annual_km_goal);
    return true;
  }, [registerForm]);
  const registerBusy = mode === 'register' && (busy || onboardingGate);
  const registerStatus = useMemo(() => {
    if (registerBackendMessage) return registerBackendMessage;
    if (registerProgress < 12) return 'Creating your account...';
    if (registerProgress < 28) return 'Evaluating your athlete identity...';
    if (registerProgress < 45) return 'Checking your current pace baseline...';
    if (registerProgress < 62) return 'Analyzing available heart-rate context...';
    if (registerProgress < 78) return 'Generating your weekly structure...';
    if (registerProgress < 92) return 'Finalizing your training plan...';
    return 'Almost done. Preparing your dashboard...';
  }, [registerProgress, registerBackendMessage]);

  useEffect(() => {
    if (!registerBusy) {
      setRegisterProgress(0);
      setRegisterHintText('');
      setRegisterBackendMessage('');
      setRegisterBackendDetails([]);
      return;
    }
    if (!registerHintText) setRegisterHintText('Preparing onboarding pipeline...');
  }, [registerBusy, onboardingGate]);

  useEffect(() => {
    if (!onboardingGate || !isAuthenticated) return;
    let mounted = true;
    let stopped = false;

    const poll = async () => {
      while (!stopped && mounted) {
        try {
          const res = await api.get('/auth/onboarding-status', { suppressToast: true } as any);
          const data = res.data || {};
          if (!mounted || stopped) return;
          const pct = Math.max(1, Math.min(100, Number(data.progress || 0)));
          setRegisterProgress((prev) => Math.max(prev, pct));
          setRegisterBackendMessage(String(data.message || 'Preparing your training setup...'));
          setRegisterBackendDetails(Array.isArray(data.details) ? data.details.map((x: any) => String(x)) : []);
          if (data.ready) {
            setRegisterProgress(100);
            setOnboardingGate(false);
            navigate('/');
            return;
          }
        } catch {
          // Keep modal visible and continue polling.
        }
        await new Promise((r) => setTimeout(r, 2500));
      }
    };
    poll();

    return () => {
      mounted = false;
      stopped = true;
    };
  }, [onboardingGate, isAuthenticated, navigate]);

  if (!loading && isAuthenticated && !onboardingGate) {
    return <Navigate to='/' replace />;
  }

  async function submitLogin() {
    setError('');
    setBusy(true);
    try {
      await login(loginForm);
      navigate('/');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Login failed.');
    } finally {
      setBusy(false);
    }
  }

  async function startStravaSignup() {
    setError('');
    setStravaBusy(true);
    try {
      const res = await api.get('/auth/strava/signup-connect');
      const url = res.data?.url;
      if (!url) throw new Error('No OAuth URL returned');
      window.location.href = url;
    } catch {
      setError('Could not start Strava OAuth. Check STRAVA_CLIENT_ID and redirect URI.');
      setStravaBusy(false);
    }
  }

  function toggleTrainingDay(day: string) {
    setRegisterForm((prev) => {
      const exists = prev.training_days.includes(day);
      return {
        ...prev,
        training_days: exists ? prev.training_days.filter((d) => d !== day) : [...prev.training_days, day],
      };
    });
  }

  async function submitRegister() {
    setError('');
    setBusy(true);
    setRegisterProgress(6);
    setRegisterBackendDetails([]);
    try {
      await register({
        ...registerForm,
        height_cm: registerForm.height_cm ? Number(registerForm.height_cm) : null,
        weight_kg: registerForm.weight_kg ? Number(registerForm.weight_kg) : null,
        goal_distance_km: registerForm.goal_distance_km ? Number(registerForm.goal_distance_km) : null,
        goal_target_time_min: registerForm.goal_target_time_min ? Number(registerForm.goal_target_time_min) : null,
        annual_km_goal: registerForm.annual_km_goal ? Number(registerForm.annual_km_goal) : null,
        ai_memory_days: registerForm.ai_memory_days ? Number(registerForm.ai_memory_days) : 30,
      });
      setOnboardingGate(true);
      setRegisterProgress((p) => Math.max(p, 14));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Registration failed.');
      setOnboardingGate(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className='min-h-screen bg-app-gradient px-4 py-8'>
      <div className='mx-auto grid w-full max-w-[1280px] items-start gap-6 md:grid-cols-[1.1fr_1fr]'>
        <Card className='hidden self-start overflow-hidden border-emerald-300/20 bg-gradient-to-br from-emerald-500/25 via-sky-500/15 to-transparent p-8 md:block'>
          <p className='text-4xl font-semibold leading-tight'>Train smarter with a real coaching cockpit.</p>
          <p className='mt-3 text-base text-slate-200/90'>Strava-first onboarding, AI week planning, and progress tracking in one flow.</p>
          <div className='mt-8 grid gap-3'>
            <div className='rounded-2xl border border-white/20 bg-slate-950/30 p-4'>
              <div className='flex items-center justify-between'>
                <p className='text-xs uppercase tracking-[0.2em] text-slate-300'>01 OAuth</p>
                <Bike className='h-4 w-4 text-sky-300' />
              </div>
              <p className='mt-2 text-lg font-semibold text-slate-100'>Connect Strava first</p>
              <p className='mt-1 text-sm text-slate-300'>Auto-prefill baseline data, then adjust manually.</p>
            </div>
            <div className='rounded-2xl border border-white/20 bg-slate-950/30 p-4'>
              <div className='flex items-center justify-between'>
                <p className='text-xs uppercase tracking-[0.2em] text-slate-300'>02 Schedule</p>
                <Calendar className='h-4 w-4 text-cyan-300' />
              </div>
              <p className='mt-2 text-lg font-semibold text-slate-100'>Select training weekdays</p>
              <p className='mt-1 text-sm text-slate-300'>AI uses availability when generating the weekly plan.</p>
            </div>
            <div className='rounded-2xl border border-white/20 bg-slate-950/30 p-4'>
              <div className='flex items-center justify-between'>
                <p className='text-xs uppercase tracking-[0.2em] text-slate-300'>03 Coaching</p>
                <Target className='h-4 w-4 text-emerald-300' />
              </div>
              <p className='mt-2 text-lg font-semibold text-slate-100'>Goal-driven weekly structure</p>
              <p className='mt-1 text-sm text-slate-300'>Each planned session gets type, zone, and coach focus notes.</p>
            </div>
          </div>
        </Card>

        <Card className='self-start p-6 md:p-7'>
          <div className='mb-4 flex gap-2 rounded-xl border border-border bg-muted/40 p-1'>
            <button type='button' onClick={() => setMode('login')} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${mode === 'login' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>Login</button>
            <button type='button' onClick={() => setMode('register')} className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${mode === 'register' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>Register</button>
          </div>

          {mode === 'login' ? (
            <div className='space-y-3'>
              <p className='text-2xl font-semibold'>Welcome back</p>
              <p className='text-sm text-muted-foreground'>Use username or email and your password.</p>
              <Input placeholder='Username or email' value={loginForm.usernameOrEmail} onChange={(e) => setLoginForm((p) => ({ ...p, usernameOrEmail: e.target.value }))} />
              <Input type='password' placeholder='Password' value={loginForm.password} onChange={(e) => setLoginForm((p) => ({ ...p, password: e.target.value }))} />
              {error && <p className='text-sm text-red-400'>{error}</p>}
              <Button className='w-full' onClick={submitLogin} disabled={busy}>{busy ? 'Signing in...' : 'Login'}</Button>
              <Button
                className='w-full'
                variant='outline'
                onClick={async () => {
                  setBusy(true);
                  try {
                    await loginAsAdmin();
                    navigate('/profile');
                  } finally {
                    setBusy(false);
                  }
                }}
                disabled={busy}
              >
                Dev: Login as admin
              </Button>
            </div>
          ) : (
            <div className='space-y-3'>
              <p className='text-2xl font-semibold'>Create athlete account</p>
              <p className='text-sm text-muted-foreground'>Start with Strava OAuth, then confirm and edit your baseline.</p>

              <Button className='w-full gap-2' onClick={startStravaSignup} disabled={busy || stravaBusy}>
                <Bike className='h-4 w-4' />
                {stravaBusy ? 'Connecting Strava...' : stravaLinkedForSignup ? 'Strava connected for signup' : 'Continue with Strava'}
              </Button>

              {stravaLinkedForSignup && (
                <div className='rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-200'>
                  <div className='flex items-center gap-3'>
                    {stravaAvatar ? <img src={stravaAvatar} alt='Strava avatar' className='h-10 w-10 rounded-full border border-emerald-300/50' /> : null}
                    <div>
                      <p className='font-medium'>Strava data imported</p>
                      <p className='text-emerald-200/80'>You can still edit every field below before registration.</p>
                    </div>
                  </div>
                </div>
              )}

              <div className='grid gap-3 md:grid-cols-2'>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Username</span>
                  <Input placeholder='felixmachan' value={registerForm.username} onChange={(e) => setRegisterForm((p) => ({ ...p, username: e.target.value }))} />
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Email</span>
                  <Input placeholder='felix@example.com' value={registerForm.email} onChange={(e) => setRegisterForm((p) => ({ ...p, email: e.target.value }))} />
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Password</span>
                  <Input type='password' placeholder='Minimum 6 characters' value={registerForm.password} onChange={(e) => setRegisterForm((p) => ({ ...p, password: e.target.value }))} />
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Display name</span>
                  <Input placeholder='Felix' value={registerForm.display_name} onChange={(e) => setRegisterForm((p) => ({ ...p, display_name: e.target.value }))} />
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Primary sport</span>
                  <select
                    className='h-10 w-full rounded-xl border border-border bg-background px-3 text-sm'
                    value={registerForm.primary_sport}
                    onChange={(e) => setRegisterForm((p) => ({ ...p, primary_sport: e.target.value }))}
                  >
                    <option value=''>Select sport</option>
                    <option value='Run'>Run</option>
                    <option value='Ride'>Ride</option>
                    <option value='Swim'>Swim</option>
                    <option value='Triathlon'>Triathlon</option>
                  </select>
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Birth date</span>
                  <Input placeholder='1995-06-10' type='date' value={registerForm.birth_date} onChange={(e) => setRegisterForm((p) => ({ ...p, birth_date: e.target.value }))} />
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Height (cm)</span>
                  <Input placeholder='178' type='number' value={registerForm.height_cm} onChange={(e) => setRegisterForm((p) => ({ ...p, height_cm: e.target.value }))} />
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Weight (kg)</span>
                  <Input placeholder='72' type='number' value={registerForm.weight_kg} onChange={(e) => setRegisterForm((p) => ({ ...p, weight_kg: e.target.value }))} />
                </label>
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Goal type</span>
                  <select
                    className='h-10 w-full rounded-xl border border-border bg-background px-3 text-sm'
                    value={registerForm.goal_type}
                    onChange={(e) => setRegisterForm((p) => ({ ...p, goal_type: e.target.value }))}
                  >
                    <option value='race'>Race goal</option>
                    <option value='time_trial'>Distance + time goal</option>
                    <option value='annual_km'>Annual distance goal</option>
                  </select>
                </label>
                {registerForm.goal_type === 'race' && (
                  <>
                    <label className='space-y-1'>
                      <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Goal event name</span>
                      <Input placeholder='Budapest Half Marathon' value={registerForm.goal_event_name} onChange={(e) => setRegisterForm((p) => ({ ...p, goal_event_name: e.target.value }))} />
                    </label>
                    <label className='space-y-1'>
                      <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Goal date</span>
                      <Input type='date' placeholder='Goal date' value={registerForm.goal_event_date} onChange={(e) => setRegisterForm((p) => ({ ...p, goal_event_date: e.target.value }))} />
                    </label>
                    <label className='space-y-1'>
                      <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Race distance (km)</span>
                      <Input type='number' step='0.1' placeholder='21.1' value={registerForm.goal_distance_km} onChange={(e) => setRegisterForm((p) => ({ ...p, goal_distance_km: e.target.value }))} />
                    </label>
                    <label className='space-y-2'>
                      <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Time goal</span>
                      <label className='flex items-center gap-2 text-sm text-slate-200'>
                        <input
                          type='checkbox'
                          checked={Boolean(registerForm.has_time_goal_for_race)}
                          onChange={(e) =>
                            setRegisterForm((p) => ({
                              ...p,
                              has_time_goal_for_race: e.target.checked,
                              goal_target_time_min: e.target.checked ? p.goal_target_time_min || '' : '',
                            }))
                          }
                        />
                        I have a time goal for this race
                      </label>
                    </label>
                    {Boolean(registerForm.has_time_goal_for_race) && (
                      <label className='space-y-1'>
                        <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Target time (min)</span>
                        <Input type='number' placeholder='110' value={registerForm.goal_target_time_min} onChange={(e) => setRegisterForm((p) => ({ ...p, goal_target_time_min: e.target.value }))} />
                      </label>
                    )}
                  </>
                )}
                {registerForm.goal_type === 'time_trial' && (
                  <>
                    <label className='space-y-1'>
                      <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Target distance (km)</span>
                      <Input type='number' step='0.1' placeholder='5' value={registerForm.goal_distance_km} onChange={(e) => setRegisterForm((p) => ({ ...p, goal_distance_km: e.target.value }))} />
                    </label>
                    <label className='space-y-1'>
                      <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Target time (min)</span>
                      <Input type='number' placeholder='20' value={registerForm.goal_target_time_min} onChange={(e) => setRegisterForm((p) => ({ ...p, goal_target_time_min: e.target.value }))} />
                    </label>
                  </>
                )}
                {registerForm.goal_type === 'annual_km' && (
                  <label className='space-y-1'>
                    <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Annual km goal</span>
                    <Input type='number' placeholder='1800' value={registerForm.annual_km_goal} onChange={(e) => setRegisterForm((p) => ({ ...p, annual_km_goal: e.target.value }))} />
                  </label>
                )}
                <label className='space-y-1'>
                  <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>AI memory window (days)</span>
                  <Input type='number' placeholder='30' value={registerForm.ai_memory_days} onChange={(e) => setRegisterForm((p) => ({ ...p, ai_memory_days: e.target.value }))} />
                </label>
              </div>

              <div className='space-y-2'>
                <p className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Preferred training days</p>
                <div className='grid grid-cols-4 gap-2 sm:grid-cols-7'>
                  {TRAINING_DAYS.map((d) => {
                    const selected = registerForm.training_days.includes(d.key);
                    return (
                      <button
                        key={d.key}
                        type='button'
                        onClick={() => toggleTrainingDay(d.key)}
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

              <label className='space-y-1'>
                <span className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Main goal and constraints</span>
                <textarea className='min-h-24 w-full rounded-xl border border-border bg-background p-3 text-sm' placeholder='Sub-1:45 half marathon while keeping recovery safe...' value={registerForm.goals} onChange={(e) => setRegisterForm((p) => ({ ...p, goals: e.target.value }))} />
              </label>

              {error && <p className='text-sm text-red-400'>{error}</p>}
              <Button className='w-full' onClick={submitRegister} disabled={!registerReady || busy}>
                {busy ? 'Creating account...' : 'Register & start onboarding'}
              </Button>
            </div>
          )}
        </Card>
      </div>
      {registerBusy && (
        <div className='fixed inset-0 z-[2500] grid place-items-center bg-slate-950/80 px-4'>
          <div className='w-full max-w-xl rounded-2xl border border-cyan-400/30 bg-slate-950/95 p-6 shadow-2xl backdrop-blur-sm'>
            <p className='text-2xl font-semibold text-cyan-100'>Generating your plan...</p>
            <p className='mt-1 text-sm text-slate-300'>Please keep this page open while onboarding finishes.</p>
            {registerBackendDetails.length > 0 ? (
              <ul className='mt-2 space-y-1 text-xs text-slate-300'>
                {registerBackendDetails.map((detail, idx) => (
                  <li key={`${detail}-${idx}`}>• {detail}</li>
                ))}
              </ul>
            ) : null}
            <div className='mt-5'>
              <div className='mb-1 flex items-center justify-between text-sm'>
                <span className='text-slate-300'>Progress</span>
                <span className='font-semibold text-cyan-200'>{registerProgress}%</span>
              </div>
              <div className='h-3 w-full overflow-hidden rounded-full border border-cyan-300/20 bg-slate-900'>
                <div
                  className='h-full rounded-full bg-gradient-to-r from-emerald-400 via-cyan-400 to-sky-400 transition-all duration-1000'
                  style={{ width: `${registerProgress}%` }}
                />
              </div>
            </div>
            <p className='mt-4 text-sm text-cyan-100/90'>{registerStatus}</p>
            <p className='mt-1 text-xs text-cyan-100/70'>{registerHintText}</p>
          </div>
        </div>
      )}
    </div>
  );
}
