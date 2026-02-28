import * as React from 'react';
import { cn } from '../../lib/utils';
import { Sparkles } from './icons';

type AiCalloutProps = React.HTMLAttributes<HTMLDivElement> & {
  title?: string;
  bodyClassName?: string;
};

export function AiCallout({ title = 'AI Response', className, bodyClassName, children, ...props }: AiCalloutProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-cyan-400/30 bg-gradient-to-r from-cyan-500/12 via-slate-900/80 to-emerald-500/12 p-3 shadow-[0_10px_30px_-20px_rgba(34,211,238,0.8)]',
        className
      )}
      {...props}
    >
      <div className='flex items-start gap-3'>
        <div className='grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-cyan-300/40 bg-cyan-500/15'>
          <Sparkles className='h-4 w-4 text-cyan-200' />
        </div>
        <div className='min-w-0 flex-1'>
          {title ? <p className='text-xs font-semibold uppercase tracking-[0.14em] text-cyan-200/90'>{title}</p> : null}
          <div className={cn(title ? 'mt-1 text-sm leading-relaxed text-cyan-50' : 'text-sm leading-relaxed text-cyan-50', bodyClassName)}>{children}</div>
        </div>
      </div>
    </div>
  );
}
