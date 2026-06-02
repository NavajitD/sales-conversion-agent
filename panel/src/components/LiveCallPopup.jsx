import { Activity, PhoneCall, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import StatusBadge from './StatusBadge';
import { cn, getSentimentTone, getOutcomeTone, titleize } from '../lib/utils';

const getSocketUrl = () => {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/panel`;
};

export default function LiveCallPopup({ parentName, callAttemptId, onClose }) {
  const [sentiment, setSentiment] = useState(null);
  const [confidence, setConfidence] = useState(null);
  const [outcome, setOutcome] = useState(null);
  const [strategy, setStrategy] = useState(null);
  const [turns, setTurns] = useState([]);
  const [status, setStatus] = useState('connecting');
  const socketRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    let disposed = false;
    const socket = new WebSocket(getSocketUrl());
    socketRef.current = socket;

    socket.onopen = () => !disposed && setStatus('live');
    socket.onerror = () => !disposed && setStatus('error');
    socket.onclose = () => !disposed && setStatus('disconnected');

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const payload = msg?.payload ?? msg?.data ?? msg;
        const inner = payload?.payload ?? payload;

        // Update live state
        if (inner?.sentiment || inner?.sentiment_end) {
          setSentiment(inner.sentiment ?? inner.sentiment_end);
        }
        if (inner?.intent_confidence !== undefined) {
          setConfidence(inner.intent_confidence);
        }
        if (inner?.next_step_label || inner?.next_step) {
          setOutcome(inner.next_step_label ?? inner.next_step);
        }
        if (inner?.strategy_applied || inner?.strategy) {
          setStrategy(inner.strategy_applied ?? inner.strategy);
        }
        if (inner?.status === 'completed' || inner?.is_final) {
          setStatus('completed');
        }

        // Add to transcript
        const utterance = inner?.utterance ?? inner?.transcript ?? inner?.message;
        if (utterance) {
          setTurns((prev) => [...prev.slice(-30), { text: utterance, ts: Date.now(), sentiment: inner?.sentiment }]);
        }
      } catch (e) { /* ignore parse errors */ }
    };

    return () => { disposed = true; socket.close(); };
  }, [callAttemptId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  const sentimentColor = sentiment
    ? getSentimentTone(sentiment) === 'success' ? 'text-emerald-500' : getSentimentTone(sentiment) === 'danger' ? 'text-rose-500' : 'text-amber-500'
    : 'text-slate-400';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative mx-4 w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl light:border-slate-200 light:bg-white"
        style={{ maxHeight: '80vh' }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Live call with ${parentName}`}
      >
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-violet-100 text-violet-600">
              <PhoneCall className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-900 light:text-slate-900">{parentName}</h3>
              <div className="flex items-center gap-2">
                <span className={cn('inline-block h-2 w-2 rounded-full', status === 'live' ? 'animate-pulse bg-emerald-500' : status === 'completed' ? 'bg-slate-400' : 'bg-amber-400')} />
                <span className="text-xs text-slate-500">{titleize(status)}</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Metrics grid */}
        <div className="mb-5 grid grid-cols-3 gap-3">
          <div className="rounded-2xl border border-slate-100 bg-slate-50 p-3 text-center light:border-slate-100 light:bg-slate-50">
            <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">Sentiment</p>
            <p className={cn('mt-1 text-lg font-bold', sentimentColor)}>{sentiment ? titleize(sentiment) : '—'}</p>
          </div>
          <div className="rounded-2xl border border-slate-100 bg-slate-50 p-3 text-center light:border-slate-100 light:bg-slate-50">
            <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">Confidence</p>
            <p className="mt-1 text-lg font-bold text-slate-800">{confidence != null ? `${(confidence * 100).toFixed(0)}%` : '—'}</p>
          </div>
          <div className="rounded-2xl border border-slate-100 bg-slate-50 p-3 text-center light:border-slate-100 light:bg-slate-50">
            <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">Expected Outcome</p>
            <p className="mt-1 text-sm font-bold text-slate-800">{outcome ? titleize(outcome) : '—'}</p>
          </div>
        </div>

        {/* Strategy badge */}
        {strategy && (
          <div className="mb-4">
            <StatusBadge tone="purple">Strategy: {titleize(strategy)}</StatusBadge>
          </div>
        )}

        {/* Live transcript */}
        <div className="rounded-2xl border border-slate-100 bg-slate-50 p-3 light:border-slate-100 light:bg-slate-50">
          <div className="mb-2 flex items-center gap-2">
            <Activity className="h-3.5 w-3.5 text-violet-500" />
            <span className="text-xs font-medium text-slate-600">Live transcript</span>
          </div>
          <div ref={scrollRef} className="max-h-48 space-y-2 overflow-y-auto pr-1">
            {turns.length === 0 && <p className="py-4 text-center text-xs text-slate-400">Waiting for speech…</p>}
            {turns.map((turn, i) => (
              <div key={i} className="rounded-xl bg-white px-3 py-2 text-sm text-slate-700 shadow-sm">
                {turn.text}
              </div>
            ))}
          </div>
        </div>

        {status === 'completed' && (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-center text-sm font-medium text-emerald-700">
            Call completed
          </div>
        )}
      </div>
    </div>
  );
}
