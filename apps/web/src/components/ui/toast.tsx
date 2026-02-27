import { useEffect, useState } from 'react';

type Toast = { id: number; title: string; message: string; type: 'success' | 'error' | 'info' };

export function ToastViewport() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const onToast = (event: Event) => {
      const detail = (event as CustomEvent).detail || {};
      const item: Toast = {
        id: Date.now(),
        title: detail.title || 'Notice',
        message: detail.message || '',
        type: detail.type || 'info',
      };
      setToasts((prev) => [...prev, item]);
      window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== item.id)), 3500);
    };

    window.addEventListener('app:toast', onToast);
    return () => window.removeEventListener('app:toast', onToast);
  }, []);

  return (
    <div className='fixed right-4 top-20 z-[2500] space-y-2'>
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`w-72 rounded-xl border bg-card p-3 shadow-lg ${
            toast.type === 'success'
              ? 'border-emerald-400/50'
              : toast.type === 'error'
              ? 'border-red-400/50'
              : 'border-border'
          }`}
        >
          <p className='text-sm font-semibold'>
            {toast.type === 'success' ? '[OK] ' : toast.type === 'error' ? '[X] ' : ''}
            {toast.title}
          </p>
          <p className='mt-1 text-xs text-muted-foreground'>{toast.message}</p>
        </div>
      ))}
    </div>
  );
}
