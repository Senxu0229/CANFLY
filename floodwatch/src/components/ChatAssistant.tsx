import { useEffect, useRef, useState, type FormEvent } from 'react';
import { formatDate } from '../lib/observations';
import type { ViewMode } from './ObservationMap';

type Citation = { id: string; title: string; url: string; excerpt: string };
type Message = { role: 'user' | 'assistant'; content: string; citations?: Citation[] };
type Reply = { answer: string; citations: Citation[]; retrieval_count: number };

type Props = {
  open: boolean;
  onClose: () => void;
  leftId: string;
  rightId: string;
  leftDate: string;
  rightDate: string;
  mode: ViewMode;
  hasAnalysis: boolean;
};

const STARTERS = ['How is possible new water detected?', 'What does orange mean?', 'Where is Kalari Abdu?'];

// Sources come from our API. Never turn a model-generated external URL into a link.
function sourceUrl(value: string): string | undefined {
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin === window.location.origin && ['http:', 'https:'].includes(url.protocol)) return url.href;
  } catch { /* Keep an invalid source title visible without an unsafe link. */ }
  return undefined;
}

function parseReply(value: unknown): Reply {
  if (!value || typeof value !== 'object') throw new Error('The assistant returned an invalid response. Please try again.');
  const reply = value as Partial<Reply>;
  if (typeof reply.answer !== 'string' || !reply.answer.trim() || !Array.isArray(reply.citations)
    || typeof reply.retrieval_count !== 'number' || !Number.isFinite(reply.retrieval_count)) {
    throw new Error('The assistant returned an incomplete response. Please try again.');
  }
  for (const source of reply.citations) {
    if (!source || !['id', 'title', 'url', 'excerpt'].every((key) => typeof source[key as keyof Citation] === 'string')) {
      throw new Error('The assistant returned invalid source information. Please try again.');
    }
  }
  return reply as Reply;
}

export function ChatAssistant({ open, onClose, leftId, rightId, leftDate, rightDate, mode, hasAnalysis }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => () => { request.current?.abort(); }, []);
  useEffect(() => {
    if (!open) return;
    input.current?.focus({ preventScroll: true });
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close.current(); }
    };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [open]);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messages, pending, error, open]);
  useEffect(() => {
    if (!open && request.current) {
      request.current.abort();
      request.current = null;
      setDraft(pending ?? '');
      setPending(null);
    }
  }, [open, pending]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setDraft('');
    setError(null);
    setPending(message);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          message,
          history: messages.slice(-6).map(({ role, content }) => ({ role, content })),
          context: { left_id: leftId, right_id: rightId, view_mode: mode },
        }),
      });
      if (!response.ok) {
        const description = response.status === 429 ? 'The assistant is busy. Please try again shortly.'
          : response.status === 400 || response.status === 422 ? 'The request could not be accepted. Check your question and try again.'
          : 'The assistant service is unavailable. Please try again once the local service is running.';
        let detail = description;
        try { const body = await response.json(); if (typeof body.error === 'string') detail = body.error.slice(0, 300); } catch { /* Proxy may return a non-JSON error. */ }
        throw new Error(detail);
      }
      const reply = parseReply(await response.json());
      if (controller.signal.aborted) return;
      setMessages((current) => [...current, { role: 'user' as const, content: message }, {
        role: 'assistant' as const, content: reply.answer, citations: reply.citations,
      }].slice(-24));
    } catch (reason: unknown) {
      if (controller.signal.aborted) return;
      setDraft(message);
      setError(reason instanceof TypeError ? 'Could not reach the assistant. Check the connection and try again.'
        : reason instanceof Error ? reason.message : 'The assistant could not answer. Please try again.');
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending(null);
        input.current?.focus({ preventScroll: true });
      }
    }
  }

  function cancel() {
    request.current?.abort();
    request.current = null;
    setDraft(pending ?? '');
    setPending(null);
    setError('Request stopped. You can edit your question and send it again.');
    input.current?.focus({ preventScroll: true });
  }

  function submit(event: FormEvent) { event.preventDefault(); void send(draft); }

  if (!open) return null;
  return <section id="assistant-panel" className="chat-panel" role="dialog" aria-modal="false" aria-labelledby="assistant-title" aria-describedby="assistant-context">
    <header className="chat-header">
      <div><span className="eyebrow">FloodWatch</span><h2 id="assistant-title">Map assistant</h2></div>
      <button type="button" className="chat-close" aria-label="Close assistant" onClick={onClose}>×</button>
    </header>
    <div className="chat-context" id="assistant-context">
      <strong>{formatDate(leftDate)} → {formatDate(rightDate)}</strong>
      <span>{hasAnalysis ? 'Candidate-water analysis available' : 'Images only · no water-area analysis for this pair'}</span>
      <small>Changing dates starts a new conversation.</small>
    </div>
    <div ref={log} className="chat-log" role="log" aria-label="Chat messages" aria-live="polite" aria-relevant="additions text" aria-busy={pending !== null}>
      {messages.length === 0 && pending === null && <div className="chat-welcome">
        <h3>Explore the evidence behind the map</h3>
        <p>Ask about the radar, study area or current comparison. Answers use local project documents and available map statistics.</p>
        <div className="chat-starters">{STARTERS.map((question) => <button type="button" key={question} onClick={() => void send(question)}>{question}</button>)}</div>
      </div>}
      {messages.map((message, index) => <article className={'chat-message ' + message.role} key={index} aria-label={message.role === 'user' ? 'Your question' : 'Assistant answer'}>
        <span className="chat-speaker">{message.role === 'user' ? 'You' : 'Map assistant'}</span>
        <p className="chat-answer">{message.content}</p>
        {message.role === 'assistant' && <div className="chat-sources">
          {message.citations?.length ? <><h3>Sources</h3><ul>{message.citations.map((citation, i) => {
            const href = sourceUrl(citation.url);
            return <li key={citation.id + ':' + i}>{href ? <a href={href} target="_blank" rel="noopener noreferrer">[{citation.id}] {citation.title} ↗</a> : <strong>[{citation.id}] {citation.title}</strong>}<details><summary>View evidence</summary><p>{citation.excerpt}</p></details></li>;
          })}</ul></> : <p>No supporting source was cited for this answer.</p>}
        </div>}
      </article>)}
      {pending !== null && <><article className="chat-message user" aria-label="Your question"><span className="chat-speaker">You</span><p className="chat-answer">{pending}</p></article><p className="chat-loading" role="status">Checking project sources and preparing an answer…</p></>}
      {error && <p className="chat-error" role="alert">{error}</p>}
    </div>
    <p className="chat-caution">Map colours show candidates, not confirmed flooding, recession or crop damage. Check the sources; evidence may be incomplete.</p>
    <form className="chat-composer" onSubmit={submit}>
      <label className="sr-only" htmlFor="assistant-question">Ask about this map</label>
      <textarea ref={input} id="assistant-question" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={1800} rows={2} placeholder="Ask about this map…" disabled={pending !== null}
        onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(draft); } }} />
      <div className="chat-composer-actions"><span>Answers in English · Enter to send</span>{pending !== null
        ? <button key="stop" className="button" type="button" onClick={(event) => { event.preventDefault(); cancel(); }}>Stop</button>
        : <button key="send" className="button primary" type="submit" disabled={!draft.trim()}>Send</button>}</div>
    </form>
  </section>;
}
