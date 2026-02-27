import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Sparkles } from '../components/ui/icons';
import { api } from '../lib/api';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';

const presetQuestions = [
  'What should be my key session in the next 48 hours?',
  'Am I ramping too fast this week?',
  'What is one adjustment for better recovery?',
  'How should I pace my next threshold workout?',
];

export function AiPage() {
  const qc = useQueryClient();
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [source, setSource] = useState('');
  const { data: settings } = useQuery({
    queryKey: ['ai-settings'],
    queryFn: async () => (await api.get('/ai/settings')).data as { memory_days: number; max_reply_chars: number },
  });
  const { data: history } = useQuery({
    queryKey: ['ai-history'],
    queryFn: async () =>
      (await api.get('/ai/history', { params: { mode: 'general_chat' } })).data as Array<{
        id: number;
        question: string;
        response_text: string;
        created_at: string;
        source: string;
      }>,
  });
  const ask = useMutation({
    mutationFn: async (q: string) =>
      (
        await api.post('/ai/ask', {
          mode: 'general_chat',
          question: q,
          max_chars: Number(settings?.max_reply_chars || 160),
          include_recent_ai_hour: true,
        })
      ).data,
    onSuccess: (res) => {
      setAnswer(res?.answer || '');
      setSource(res?.source || '');
      qc.invalidateQueries({ queryKey: ['ai-history'] });
    },
  });

  return (
    <div className='space-y-4'>
      <Card className='p-6'>
        <p className='flex items-center gap-2 text-2xl font-semibold'><Sparkles className='h-5 w-5 text-cyan-300' />AI Coach Console</p>
        <p className='mt-1 text-sm text-muted-foreground'>Memory window: {settings?.memory_days ?? 30} days. Ask preset or custom questions from your current training data.</p>
        <div className='mt-4 grid gap-2 md:grid-cols-2'>
          {presetQuestions.map((q) => (
            <Button key={q} variant='outline' onClick={() => ask.mutate(q)} disabled={ask.isPending}>
              {q}
            </Button>
          ))}
        </div>
        <div className='mt-4 rounded-xl border border-border p-3'>
          <label className='text-sm text-muted-foreground'>Custom question</label>
          <textarea
            className='mt-2 min-h-20 w-full rounded-xl border border-border bg-background p-3 text-sm'
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder='Write your own coaching question...'
          />
          <div className='mt-2'>
            <Button onClick={() => ask.mutate(question)} disabled={ask.isPending || !question.trim()}>
              <MessageSquare className='h-4 w-4' /> Ask AI
            </Button>
          </div>
        </div>
        {answer ? (
          <div className='mt-4 rounded-xl border border-cyan-400/40 bg-cyan-500/10 p-3 text-sm text-cyan-100'>
            {source && (
              <p className='mb-2 text-xs uppercase tracking-wide text-cyan-200/80'>
                source: {source}
              </p>
            )}
            {answer}
          </div>
        ) : null}

        <div className='mt-4 rounded-xl border border-border p-3'>
          <p className='text-sm font-semibold'>History</p>
          <div className='mt-2 max-h-72 space-y-2 overflow-y-auto pr-1'>
            {(history || []).length === 0 ? (
              <p className='text-sm text-muted-foreground'>No AI questions yet.</p>
            ) : (
              (history || []).map((row) => (
                <div key={row.id} className='rounded-lg border border-border bg-muted/20 p-3'>
                  <p className='text-xs text-muted-foreground'>{new Date(row.created_at).toLocaleString()} | {row.source}</p>
                  <p className='mt-1 text-sm font-medium'>{row.question || 'Question unavailable'}</p>
                  <p className='mt-1 text-sm text-muted-foreground'>{row.response_text}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
