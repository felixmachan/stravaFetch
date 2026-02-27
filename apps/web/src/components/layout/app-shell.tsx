import { Activity, Gauge, LogOut, MessageSquare, Moon, Settings2, Sun, UserCircle2 } from '../ui/icons';
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/auth-context';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';

const navItems = [
  { to: '/', label: 'Dashboard', icon: Gauge },
  { to: '/activities', label: 'Activities', icon: Activity },
  { to: '/plan', label: 'Plan', icon: Activity },
  { to: '/ai', label: 'AI', icon: MessageSquare },
  { to: '/profile', label: 'Profile', icon: UserCircle2 },
  { to: '/settings', label: 'Settings', icon: Settings2 },
];

export function AppShell() {
  const { user, stravaConnected, logout } = useAuth();
  const [dark, setDark] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
  }, [dark]);

  return (
    <div className='min-h-screen bg-app-gradient text-foreground'>
      <header className='sticky top-0 z-[1200] border-b border-border/70 bg-background/90 backdrop-blur'>
        <div className='mx-auto flex h-16 max-w-[1720px] items-center justify-between px-5'>
          <Link to='/' className='text-lg font-semibold tracking-tight'>PacePilot</Link>
          <div className='flex items-center gap-2'>
            <Badge className={stravaConnected ? 'border-emerald-400/40 text-emerald-300' : ''}>
              {stravaConnected ? 'Strava Connected' : 'Strava Not Connected'}
            </Badge>
            <Button variant='ghost' size='sm' onClick={() => setDark((v) => !v)}>{dark ? <Sun className='h-4 w-4' /> : <Moon className='h-4 w-4' />}</Button>
            {user && <Badge>{user.username}</Badge>}
            <Button
              variant='ghost'
              size='sm'
              onClick={async () => {
                await logout();
                navigate('/login');
              }}
            >
              <LogOut className='h-4 w-4' />
            </Button>
          </div>
        </div>
      </header>

      <div className='mx-auto grid max-w-[1720px] gap-5 px-5 py-5 md:grid-cols-[17rem_1fr]'>
        <aside className='rounded-2xl border border-border bg-card p-3 h-fit'>
          <nav className='space-y-1'>
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-xl px-3 py-2 text-base transition ${isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`
                  }
                >
                  <Icon className='h-4 w-4' />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <main className='space-y-4'>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
