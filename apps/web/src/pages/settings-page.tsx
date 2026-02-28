import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Link2, MessageSquare, RefreshCcw, Settings2, Unplug } from '../components/ui/icons';
import { api } from '../lib/api';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { useAuth } from '../context/auth-context';

export function SettingsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { stravaConnected, refreshMe, logout } = useAuth();
  const [searchParams] = useSearchParams();
  const { data } = useQuery({
    queryKey: ['ai-settings'],
    queryFn: async () => (await api.get('/ai/settings')).data as { memory_days: number; max_reply_chars: number },
  });
  const [memoryDays, setMemoryDays] = useState(30);
  const [maxChars, setMaxChars] = useState(500);
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [manualCode, setManualCode] = useState('');
  const { data: telegramSetup } = useQuery({
    queryKey: ['telegram-setup'],
    queryFn: async () =>
      (await api.get('/integrations/telegram/setup')).data as {
        enabled: boolean;
        connected: boolean;
        bot_username: string;
        setup_code: string;
        setup_code_expires_at: string | null;
        telegram_username: string;
        telegram_chat_id: string;
      },
  });

  useEffect(() => {
    if (data) {
      setMemoryDays(data.memory_days ?? 30);
        setMaxChars(data.max_reply_chars ?? 500);
    }
  }, [data]);
  useEffect(() => {
    const s = searchParams.get('strava');
    if (s === 'connected') {
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Strava connected', message: 'Your account is linked and ready to sync.' } }));
      refreshMe();
      qc.invalidateQueries({ queryKey: ['activities'] });
    }
    if (s === 'error') {
      const reason = searchParams.get('reason') || 'unknown';
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Strava connect failed', message: `Reason: ${reason}` } }));
    }
  }, [searchParams]);

  const connect = useMutation({
    mutationFn: async () => (await api.get('/auth/strava/connect')).data,
    onSuccess: (res) => {
      window.location.href = res.url;
    },
  });

  const disconnect = useMutation({
    mutationFn: async () => api.post('/auth/strava/disconnect'),
    onSuccess: async () => {
      await refreshMe();
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Strava disconnected', message: 'Connection removed from this account.' } }));
    },
  });

  const syncNow = useMutation({
    mutationFn: async () => (await api.post('/strava/sync-now')).data,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['activities'] });
      const synced = res?.synced === true;
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: synced ? 'Sync completed' : 'Sync queued',
            message: synced
              ? `Fetched: ${res?.result?.fetched ?? 0}, imported: ${res?.result?.upserted ?? 0}`
              : 'Background sync started.',
          },
        })
      );
    },
  });

  const demoImport = useMutation({
    mutationFn: async () => api.post('/demo/import'),
    onSuccess: async () => {
      await refreshMe();
      qc.invalidateQueries({ queryKey: ['activities'] });
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Demo imported', message: 'A sample activity was added to your timeline.' } }));
    },
  });

  const generateTelegramCode = useMutation({
    mutationFn: async () => (await api.post('/integrations/telegram/generate-code')).data,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['telegram-setup'] });
      setManualCode(res?.setup_code || '');
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: '[✓] Telegram setup code ready',
            message: res?.instruction || 'Send the code to your Telegram bot and click Verify.',
          },
        })
      );
    },
    onError: (err: any) => {
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: '[x] Telegram code generation failed',
            message: err?.response?.data?.detail || 'Could not generate setup code.',
          },
        })
      );
    },
  });

  const verifyTelegram = useMutation({
    mutationFn: async () => (await api.post('/integrations/telegram/verify', { code: manualCode || telegramSetup?.setup_code || '' })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['telegram-setup'] });
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: '[✓] Telegram connected',
            message: 'Notifications can now be delivered to your Telegram chat.',
          },
        })
      );
    },
    onError: (err: any) => {
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: '[x] Telegram verify failed',
            message: err?.response?.data?.detail || 'No matching setup message found yet.',
          },
        })
      );
    },
  });

  const disconnectTelegram = useMutation({
    mutationFn: async () => (await api.post('/integrations/telegram/disconnect')).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['telegram-setup'] });
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: 'Telegram disconnected',
            message: 'Chat link removed for this account.',
          },
        })
      );
    },
  });

  const testTelegram = useMutation({
    mutationFn: async () => (await api.post('/integrations/test-telegram')).data,
    onSuccess: () => {
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: '[✓] Test message queued',
            message: 'A test Telegram message was queued.',
          },
        })
      );
    },
  });

  const save = useMutation({
    mutationFn: async () => api.patch('/ai/settings', { memory_days: memoryDays, max_reply_chars: maxChars }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ai-settings'] });
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Settings saved', message: 'AI memory settings updated.' } }));
    },
  });
  const deleteAccount = useMutation({
    mutationFn: async () => (await api.delete('/auth/delete-account')).data,
    onSuccess: async () => {
      await logout();
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { title: 'Account deleted', message: 'Your account and related data were removed.' } }));
      navigate('/login', { replace: true });
    },
    onError: (err: any) => {
      window.dispatchEvent(
        new CustomEvent('app:toast', {
          detail: {
            title: 'Delete failed',
            message: err?.response?.data?.detail || 'Could not delete account.',
          },
        })
      );
    },
  });

  return (
    <div className='space-y-4'>
      
      <Card className='p-6'>
        <p className='flex items-center gap-2 text-2xl font-semibold'><Link2 className='h-5 w-5 text-cyan-300' />Integrations</p>
        <p className='mt-1 text-sm text-muted-foreground'>Manage data providers and sync actions.</p>
        <div className='mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border p-4'>
          <div>
            <p className='text-lg font-semibold'>Strava</p>
            <p className='text-sm text-muted-foreground'>{stravaConnected ? 'Connected and ready to sync.' : 'Not connected yet.'}</p>
          </div>
          <div className='flex items-center gap-2'>
            {stravaConnected && (
              <Button variant='outline' onClick={() => syncNow.mutate()} disabled={syncNow.isPending}>
                <RefreshCcw className='h-4 w-4' /> {syncNow.isPending ? 'Syncing...' : 'Sync now'}
              </Button>
            )}
            {stravaConnected ? (
              <Button variant='danger' onClick={() => disconnect.mutate()}>
                <Unplug className='h-4 w-4' /> Disconnect
              </Button>
            ) : (
              <Button onClick={() => connect.mutate()}>
                <Link2 className='h-4 w-4' /> Connect Strava
              </Button>
            )}
          </div>
        </div>
        <div className='mt-3 rounded-xl border border-border p-4'>
          <p className='text-sm text-muted-foreground'>No data yet? Import a demo activity for dashboard/charts testing.</p>
          <Button className='mt-3' variant='outline' onClick={() => demoImport.mutate()}>
            Import Demo Activity
          </Button>
        </div>

        <div className='mt-4 rounded-xl border border-border p-4'>
          <p className='flex items-center gap-2 text-lg font-semibold'><MessageSquare className='h-5 w-5 text-cyan-300' />Telegram Setup</p>
          <p className='mt-1 text-sm text-muted-foreground'>
            Step-by-step linking for Telegram notifications.
          </p>
          {!telegramSetup?.enabled && (
            <div className='mt-3 rounded-lg border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-200'>
              TELEGRAM_BOT_TOKEN is not configured on backend. Add it in `.env` first.
            </div>
          )}
          <div className='mt-4 grid gap-3 md:grid-cols-3'>
            <div className='rounded-lg border border-border p-3'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Step 1</p>
              <p className='mt-1 text-sm'>Generate your one-time setup code.</p>
            </div>
            <div className='rounded-lg border border-border p-3'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Step 2</p>
              <p className='mt-1 text-sm'>Open bot and send: <span className='font-semibold'>/start CODE</span></p>
              {telegramSetup?.bot_username && (
                <p className='mt-1 text-xs text-cyan-300'>Bot: @{telegramSetup.bot_username}</p>
              )}
            </div>
            <div className='rounded-lg border border-border p-3'>
              <p className='text-xs uppercase tracking-wide text-muted-foreground'>Step 3</p>
              <p className='mt-1 text-sm'>Click verify and finish setup.</p>
            </div>
          </div>

          <div className='mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto_auto]'>
            <Input
              value={manualCode}
              onChange={(e) => setManualCode(e.target.value.toUpperCase())}
              placeholder={telegramSetup?.setup_code || 'Setup code (e.g. PP12AB34)'}
            />
            <Button
              variant='outline'
              onClick={() => generateTelegramCode.mutate()}
              disabled={!telegramSetup?.enabled || generateTelegramCode.isPending}
            >
              {generateTelegramCode.isPending ? 'Generating...' : 'Generate code'}
            </Button>
            <Button onClick={() => verifyTelegram.mutate()} disabled={!telegramSetup?.enabled || verifyTelegram.isPending}>
              {verifyTelegram.isPending ? 'Verifying...' : 'Verify'}
            </Button>
            {telegramSetup?.connected ? (
              <Button variant='danger' onClick={() => disconnectTelegram.mutate()}>
                Disconnect
              </Button>
            ) : null}
          </div>

          <div className='mt-3 rounded-lg border border-border p-3 text-sm'>
            <p className='text-muted-foreground'>
              Status: {telegramSetup?.connected ? 'Connected' : 'Not connected'}
            </p>
            {telegramSetup?.telegram_chat_id && (
              <p className='text-muted-foreground'>Chat ID: {telegramSetup.telegram_chat_id}</p>
            )}
            {telegramSetup?.telegram_username && (
              <p className='text-muted-foreground'>Telegram user: @{telegramSetup.telegram_username}</p>
            )}
          </div>

          <div className='mt-3'>
            <Button variant='outline' onClick={() => testTelegram.mutate()} disabled={!telegramSetup?.connected || testTelegram.isPending}>
              {testTelegram.isPending ? 'Sending...' : 'Send test Telegram message'}
            </Button>
          </div>
        </div>
      </Card>

      <Card className='p-6'>
        <p className='flex items-center gap-2 text-2xl font-semibold'><Settings2 className='h-5 w-5 text-cyan-300' />AI Settings</p>
        <p className='mt-1 text-sm text-muted-foreground'>Control how much context the AI keeps when evaluating workouts and answering questions.</p>
        <div className='mt-4 grid gap-4 md:grid-cols-2'>
          <label className='space-y-1'>
            <span className='text-sm text-muted-foreground'>AI memory window (days)</span>
            <Input type='number' value={memoryDays} onChange={(e) => setMemoryDays(Number(e.target.value || 30))} />
          </label>
          <label className='space-y-1'>
            <span className='text-sm text-muted-foreground'>Max AI reply chars</span>
              <Input type='number' min={40} max={500} value={maxChars} onChange={(e) => setMaxChars(Number(e.target.value || 500))} />
          </label>
        </div>
        <div className='mt-4'>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save settings'}</Button>
        </div>
      </Card>

      <Card className='border-rose-500/40 bg-rose-500/5 p-6'>
        <p className='flex items-center gap-2 text-2xl font-semibold text-rose-200'><AlertTriangle className='h-5 w-5 text-rose-300' />Danger Zone</p>
        <p className='mt-1 text-sm text-rose-100/80'>
          Delete your account and all related data (activities, plans, notes, integrations). This action cannot be undone.
        </p>
        <div className='mt-4 grid gap-3 md:grid-cols-[1fr_auto]'>
          <Input
            value={deleteConfirm}
            onChange={(e) => setDeleteConfirm(e.target.value)}
            placeholder='Type DELETE to confirm'
          />
          <Button
            variant='danger'
            onClick={() => deleteAccount.mutate()}
            disabled={deleteAccount.isPending || deleteConfirm !== 'DELETE'}
          >
            {deleteAccount.isPending ? 'Deleting account...' : 'Delete account'}
          </Button>
        </div>
      </Card>
    </div>
  );
}
