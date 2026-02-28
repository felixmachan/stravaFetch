import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Sparkles } from '../components/ui/icons';
import { api } from '../lib/api';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useAuth } from '../context/auth-context';

type ChatSession = {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string;
};

type ChatMessage = {
  id: number;
  session_id: number;
  role: 'user' | 'assistant';
  content: string;
  source?: string;
  model?: string;
  created_at: string;
};

function toChatTitle(question: string) {
  const value = String(question || '').trim();
  if (!value) return 'New chat';
  return value.slice(0, 80).trim() || 'New chat';
}

function renderInlineMarkdown(text: string) {
  const parts: Array<{ t: string; bold?: boolean; code?: boolean }> = [];
  const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null = null;
  while ((m = tokenRegex.exec(text)) !== null) {
    if (m.index > last) parts.push({ t: text.slice(last, m.index) });
    const token = m[0] || '';
    if (token.startsWith('**') && token.endsWith('**')) parts.push({ t: token.slice(2, -2), bold: true });
    else if (token.startsWith('`') && token.endsWith('`')) parts.push({ t: token.slice(1, -1), code: true });
    else parts.push({ t: token });
    last = m.index + token.length;
  }
  if (last < text.length) parts.push({ t: text.slice(last) });
  return parts.map((p, idx) => {
    if (p.code) return <code key={idx} className='rounded bg-slate-900/70 px-1 py-0.5 text-cyan-100'>{p.t}</code>;
    if (p.bold) return <strong key={idx} className='font-semibold text-slate-100'>{p.t}</strong>;
    return <span key={idx}>{p.t}</span>;
  });
}

function MarkdownPreview({ text, className = '' }: { text: string; className?: string }) {
  const lines = (text || '').replace(/\r/g, '').split('\n');
  const blocks: JSX.Element[] = [];
  let listItems: string[] = [];
  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`list-${blocks.length}`} className='ml-5 list-disc space-y-1'>
        {listItems.map((item, idx) => <li key={idx}>{renderInlineMarkdown(item)}</li>)}
      </ul>
    );
    listItems = [];
  };
  for (const rawLine of lines) {
    const t = rawLine.trim();
    if (!t) {
      flushList();
      blocks.push(<div key={`sp-${blocks.length}`} className='h-2' />);
      continue;
    }
    const bullet = t.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      listItems.push(bullet[1]);
      continue;
    }
    flushList();
    const h3 = t.match(/^###\s+(.+)$/);
    const h2 = t.match(/^##\s+(.+)$/);
    const h1 = t.match(/^#\s+(.+)$/);
    if (h3) blocks.push(<h3 key={`h3-${blocks.length}`} className='text-base font-semibold text-slate-100'>{renderInlineMarkdown(h3[1])}</h3>);
    else if (h2) blocks.push(<h2 key={`h2-${blocks.length}`} className='text-lg font-semibold text-slate-100'>{renderInlineMarkdown(h2[1])}</h2>);
    else if (h1) blocks.push(<h1 key={`h1-${blocks.length}`} className='text-xl font-semibold text-slate-100'>{renderInlineMarkdown(h1[1])}</h1>);
    else blocks.push(<p key={`p-${blocks.length}`}>{renderInlineMarkdown(t)}</p>);
  }
  flushList();
  return <div className={`space-y-1 whitespace-pre-wrap text-slate-200 ${className}`}>{blocks}</div>;
}

export function AiPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [question, setQuestion] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [cursorOn, setCursorOn] = useState(true);
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [liveTarget, setLiveTarget] = useState('');
  const [liveTyped, setLiveTyped] = useState('');
  const [isDraftChat, setIsDraftChat] = useState(false);
  const [typingTitleSessionId, setTypingTitleSessionId] = useState<number | null>(null);
  const [typingTitleTarget, setTypingTitleTarget] = useState('');
  const [typingTitleValue, setTypingTitleValue] = useState('');
  const [sessionTitleOverrides, setSessionTitleOverrides] = useState<Record<number, string>>({});
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: async () => (await api.get('/profile')).data as { display_name?: string },
  });

  const { data: settings } = useQuery({
    queryKey: ['ai-settings'],
    queryFn: async () => (await api.get('/ai/settings')).data as { memory_days: number; max_reply_chars: number },
  });
  const { data: sessions } = useQuery({
    queryKey: ['ai-chat-sessions'],
    queryFn: async () => (await api.get('/ai/chat/sessions')).data as ChatSession[],
  });
  const { data: messages } = useQuery({
    queryKey: ['ai-chat-messages', activeSessionId],
    queryFn: async () => (await api.get('/ai/chat/messages', { params: { session_id: activeSessionId } })).data as ChatMessage[],
    enabled: Boolean(activeSessionId),
  });

  useEffect(() => {
    if (isDraftChat) return;
    if (!activeSessionId && (sessions || []).length > 0) setActiveSessionId((sessions || [])[0].id);
  }, [sessions, activeSessionId, isDraftChat]);

  const deleteSession = useMutation({
    mutationFn: async (id: number) => (await api.delete(`/ai/chat/sessions/${id}`)).data,
    onSuccess: async (_res, id) => {
      await qc.invalidateQueries({ queryKey: ['ai-chat-sessions'] });
      if (activeSessionId === id) {
        const remaining = (sessions || []).filter((s) => s.id !== id);
        setActiveSessionId(remaining.length > 0 ? remaining[0].id : null);
      }
    },
  });

  const ask = useMutation({
    mutationFn: async (q: string) =>
      (
        await api.post('/ai/ask', {
          mode: 'general_chat',
          question: q,
          session_id: activeSessionId,
          max_chars: Number(settings?.max_reply_chars || 500),
          include_recent_ai_hour: false,
        })
      ).data as { answer: string; source: string; interaction_id: number; session_id?: number | null },
    onMutate: (q) => {
      setPendingQuestion(q);
      setLiveTarget('');
      setLiveTyped('');
      setQuestion('');
    },
    onSuccess: async (res, q) => {
      const createdNow = Boolean(!activeSessionId && res?.session_id);
      if (res?.session_id && !activeSessionId) {
        const sid = Number(res.session_id);
        setActiveSessionId(sid);
        setIsDraftChat(false);
        const target = toChatTitle(q);
        setTypingTitleSessionId(sid);
        setTypingTitleTarget(target);
        setTypingTitleValue('New chat');
        setSessionTitleOverrides((prev) => ({ ...prev, [sid]: 'New chat' }));
      }
      setLiveTarget(res?.answer || '');
      setLiveTyped('');
      if (!createdNow) {
        setTypingTitleSessionId(null);
        setTypingTitleTarget('');
        setTypingTitleValue('');
      }
    },
    onError: () => {
      setPendingQuestion('');
      setLiveTarget('');
      setLiveTyped('');
    },
  });

  const liveIsTyping = Boolean(liveTarget) && liveTyped.length < liveTarget.length;
  const showCursor = ask.isPending || liveIsTyping;

  useEffect(() => {
    if (!liveTarget || liveTyped.length >= liveTarget.length) return;
    const t = setTimeout(() => {
      const nextLen = Math.min(liveTarget.length, liveTyped.length + 2);
      setLiveTyped(liveTarget.slice(0, nextLen));
    }, 18);
    return () => clearTimeout(t);
  }, [liveTarget, liveTyped]);

  useEffect(() => {
    if (!showCursor) return;
    const t = setInterval(() => setCursorOn((v) => !v), 450);
    return () => clearInterval(t);
  }, [showCursor]);

  useEffect(() => {
    if (!typingTitleSessionId || !typingTitleTarget) return;
    if (typingTitleValue === typingTitleTarget) {
      setSessionTitleOverrides((prev) => ({ ...prev, [typingTitleSessionId]: typingTitleTarget }));
      setTypingTitleSessionId(null);
      setTypingTitleTarget('');
      return;
    }
    const t = setTimeout(() => {
      const nextLen = Math.min(typingTitleTarget.length, typingTitleValue.length + 2);
      const next = typingTitleTarget.slice(0, nextLen);
      setTypingTitleValue(next);
      setSessionTitleOverrides((prev) => ({ ...prev, [typingTitleSessionId]: next }));
    }, 18);
    return () => clearTimeout(t);
  }, [typingTitleSessionId, typingTitleTarget, typingTitleValue]);

  useEffect(() => {
    if (!liveTarget) return;
    if (liveTyped.length < liveTarget.length) return;
    setPendingQuestion('');
    setLiveTarget('');
    setLiveTyped('');
    qc.invalidateQueries({ queryKey: ['ai-chat-sessions'] });
    qc.invalidateQueries({ queryKey: ['ai-chat-messages', activeSessionId] });
  }, [liveTyped, liveTarget, qc, activeSessionId]);

  const mergedMessages = useMemo(() => {
    const rows = [...(messages || [])];
    if (pendingQuestion) {
      rows.push({
        id: -1,
        session_id: activeSessionId || -1,
        role: 'user',
        content: pendingQuestion,
        created_at: new Date().toISOString(),
      });
      rows.push({
        id: -2,
        session_id: activeSessionId || -1,
        role: 'assistant',
        content: ask.isPending ? '' : liveTyped,
        created_at: new Date().toISOString(),
      });
    }
    return rows;
  }, [messages, pendingQuestion, ask.isPending, liveTyped, activeSessionId]);

  const askNow = (q: string) => {
    const value = q.trim();
    if (!value || ask.isPending) return;
    ask.mutate(value);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [mergedMessages.length, liveTyped, ask.isPending]);

  const userDisplayName = String(profile?.display_name || user?.username || 'You').trim();
  const hasConversation = mergedMessages.length > 0;
  const panelHeightClass = hasConversation ? 'h-[540px] md:h-[630px]' : 'h-[360px] md:h-[420px]';
  const activeSession = (sessions || []).find((s) => s.id === activeSessionId) || null;
  const activeTitle = activeSession?.title?.trim() || 'New chat';
  const renderedSessions: Array<ChatSession & { isDraft?: boolean }> = useMemo(() => {
    const base = [...(sessions || [])];
    if (isDraftChat && !activeSessionId) {
      return [
        {
          id: -1,
          title: 'New chat',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_message_preview: '',
          isDraft: true,
        },
        ...base,
      ];
    }
    return base;
  }, [sessions, isDraftChat, activeSessionId]);

  return (
    <div className='space-y-4'>
      <Card className='p-4'>
        <p className='flex items-center gap-2 text-2xl font-semibold'><Sparkles className='h-5 w-5 text-cyan-300' />AI Coach Console</p>
        <p className='mt-1 text-sm text-muted-foreground'>Memory window: {settings?.memory_days ?? 30} days.</p>
      </Card>

      <div className='grid items-start gap-4 lg:grid-cols-[280px_1fr]'>
        <Card className='self-start p-4'>
          <div className='flex items-center justify-between'>
            <p className='flex items-center gap-2 text-lg font-semibold'><Sparkles className='h-4 w-4 text-cyan-300' />Chats</p>
            <Button
              size='sm'
              variant='outline'
              onClick={() => {
                setActiveSessionId(null);
                setIsDraftChat(true);
                setQuestion('');
                setPendingQuestion('');
                setLiveTarget('');
                setLiveTyped('');
              }}
            >
              New
            </Button>
          </div>
          <div className='mt-3 max-h-[68vh] space-y-2 overflow-y-auto pr-1'>
            {renderedSessions.length === 0 ? (
              <p className='text-sm text-muted-foreground'>No conversations yet.</p>
            ) : (
              renderedSessions.map((s) => (
                <button
                  key={s.id}
                  type='button'
                  onClick={() => {
                    if (s.id < 0 || s.isDraft) {
                      setActiveSessionId(null);
                      setIsDraftChat(true);
                      return;
                    }
                    setIsDraftChat(false);
                    setActiveSessionId(s.id);
                  }}
                  className={`w-full rounded-xl border px-3 py-2 text-left transition ${(s.id < 0 || s.isDraft ? !activeSessionId : activeSessionId === s.id) ? 'border-cyan-400/60 bg-cyan-500/10' : 'border-border bg-muted/20 hover:border-cyan-400/40'}`}
                >
                  <p className='truncate text-sm font-semibold'>{(s.id > 0 ? sessionTitleOverrides[s.id] : undefined) || s.title || 'New chat'}</p>
                  <p className='mt-1 truncate text-xs text-muted-foreground'>{s.last_message_preview || new Date(s.updated_at).toLocaleString()}</p>
                </button>
              ))
            )}
          </div>
        </Card>

        <Card className='flex min-h-[72vh] flex-col p-4'>
          <div className='flex items-center justify-between gap-3'>
            <p className='truncate text-xl font-semibold'>{activeTitle}</p>
            <Button
              size='sm'
              variant='outline'
              className='border-rose-500/50 bg-rose-500/10 text-rose-200 hover:border-rose-400 hover:bg-rose-500/20'
              onClick={() => activeSessionId && deleteSession.mutate(activeSessionId)}
              disabled={!activeSessionId || deleteSession.isPending}
            >
              Delete
            </Button>
          </div>

          <div className={`mt-4 ${panelHeightClass} flex flex-col gap-3 overflow-y-auto rounded-xl border border-border bg-muted/10 p-3 transition-all duration-300 ease-out`}>
            {mergedMessages.length === 0 ? (
              <p className='text-sm text-muted-foreground'>Start a conversation with a question.</p>
            ) : (
              mergedMessages.map((m) => {
                if (m.role === 'user') {
                  return (
                    <div
                      key={`${m.id}-${m.created_at}`}
                      className='flex w-full'
                      style={{ justifyContent: 'flex-end' }}
                    >
                      <div className='flex flex-col items-end' style={{ maxWidth: '560px', width: 'fit-content' }}>
                        <p className='mb-1 text-right text-xs text-cyan-200/90'>{userDisplayName}</p>
                        <div className='inline-block rounded-2xl border border-cyan-400/40 bg-cyan-500/15 px-4 py-3 text-sm text-cyan-50'>
                          <p className='whitespace-pre-wrap'>{m.content}</p>
                        </div>
                      </div>
                    </div>
                  );
                }
                return (
                  <div
                    key={`${m.id}-${m.created_at}`}
                    className='flex w-full'
                    style={{ justifyContent: 'flex-start' }}
                  >
                    <div className='flex flex-col items-start' style={{ maxWidth: '700px', width: 'fit-content' }}>
                      <p className='mb-1 text-left text-xs text-slate-300/90'>Coach</p>
                      <div className='inline-block rounded-2xl border border-border bg-slate-950/70 px-4 py-3 text-sm text-slate-100'>
                        <MarkdownPreview text={m.content || ''} />
                        {m.id === -2 && showCursor ? <span className={`${cursorOn ? 'opacity-100' : 'opacity-0'} transition-opacity`}>|</span> : null}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className='mt-3 rounded-xl border border-border p-3'>
            <label className='text-sm text-muted-foreground'>Message</label>
            <textarea
              className='mt-2 min-h-20 w-full rounded-xl border border-border bg-background p-3 text-sm'
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder='Write your coaching question...'
            />
            <div className='mt-2 flex items-center gap-2'>
              <Button onClick={() => askNow(question)} disabled={ask.isPending || !question.trim()}>
                <MessageSquare className='h-4 w-4' /> Send
              </Button>
              {!activeSessionId ? <span className='text-xs text-muted-foreground'>Chat will be saved only after first AI answer.</span> : null}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
