import { Link2, RefreshCcw, Unplug } from '../components/ui/icons';
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../context/auth-context';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';

export function IntegrationsPage() {
  const { stravaConnected, refreshMe } = useAuth();
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();

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

  return (
    <div className='space-y-4'>
      <Card>
        <div className='flex items-center justify-between'>
          <div>
            <p className='text-lg font-semibold'>Strava Integration</p>
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
      </Card>

      <Card>
        <p className='text-lg font-semibold'>No data yet?</p>
        <p className='text-sm text-muted-foreground'>Import a demo activity to test dashboard charts and activity detail UX without Strava.</p>
        <Button className='mt-3' variant='outline' onClick={() => demoImport.mutate()}>
          Import Demo Activity
        </Button>
      </Card>
    </div>
  );
}
