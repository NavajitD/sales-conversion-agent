import { BellRing, CalendarClock, CheckCircle2, PhoneCall } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import PanelCard from '../components/PanelCard';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { useApi } from '../hooks/useApi';
import {
  formatDateTime,
  formatRelativeTime,
  getStatusTone,
  safeNumber,
  sortByDate,
  titleize,
} from '../lib/utils';

const storageKey = 'aria-crm-callbacks-done';

export default function CallbacksPage() {
  const { data, loading, error, refetch } = useApi('/api/dashboard/callbacks', {
    initialData: { callbacks: [] },
  });
  const [completedIds, setCompletedIds] = useState(() => {
    if (typeof window === 'undefined') return [];
    try {
      return JSON.parse(window.localStorage.getItem(storageKey) ?? '[]');
    } catch {
      return [];
    }
  });

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(completedIds));
  }, [completedIds]);

  const completedLookup = useMemo(() => new Set(completedIds.map(String)), [completedIds]);
  const callbacks = useMemo(() => sortByDate(data?.callbacks ?? [], 'scheduled_at', 'asc'), [data]);
  const pendingCallbacks = callbacks.filter((callback) => !completedLookup.has(String(callback.id)));
  const overdueCount = pendingCallbacks.filter((callback) => new Date(callback.scheduled_at).getTime() < Date.now()).length;
  const repeatedAttempts = pendingCallbacks.filter((callback) => safeNumber(callback.attempts_so_far) >= 2).length;

  const markDone = (id) => {
    setCompletedIds((current) => (current.includes(String(id)) ? current : [...current, String(id)]));
  };

  if (loading) return <LoadingState label="Loading callback queue" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={BellRing} label="Pending callbacks" value={pendingCallbacks.length} hint="Callbacks waiting for a counselor action" />
        <StatCard icon={CalendarClock} label="Overdue" value={overdueCount} hint="Scheduled follow-ups that are past due" />
        <StatCard icon={PhoneCall} label="Repeat attempts" value={repeatedAttempts} hint="Callbacks already attempted multiple times" />
        <StatCard icon={CheckCircle2} label="Done this session" value={completedIds.length} hint="UI-only completion state saved locally" />
      </div>

      <PanelCard title="Pending callback queue" subtitle="Callbacks are sorted by scheduled time so your team can prioritize the next commitment.">
        <div className="space-y-4">
          {pendingCallbacks.length ? (
            pendingCallbacks.map((callback) => {
              const isOverdue = new Date(callback.scheduled_at).getTime() < Date.now();
              return (
                <div
                  key={callback.id}
                  className="flex flex-col gap-4 rounded-3xl border border-slate-800/80 bg-slate-950/60 p-5 transition hover:border-[#7C3AED]/25 hover:bg-slate-900/70 light:border-slate-200 light:bg-white light:hover:border-violet-200 light:hover:bg-violet-50/30 lg:flex-row lg:items-center lg:justify-between"
                >
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-semibold text-white light:text-slate-900">{callback.parent_name}</h3>
                      <StatusBadge tone={getStatusTone(callback.status)}>{titleize(callback.status)}</StatusBadge>
                      {isOverdue && <StatusBadge tone="danger">Overdue</StatusBadge>}
                    </div>
                    <p className="text-sm text-slate-400 light:text-slate-500">{callback.phone || '—'}</p>
                    <div className="flex flex-wrap gap-2">
                      <StatusBadge tone="warning">Reason: {titleize(callback.reason, 'Unknown')}</StatusBadge>
                      <StatusBadge tone="purple">Attempts: {safeNumber(callback.attempts_so_far)}</StatusBadge>
                    </div>
                    {callback.notes && <p className="max-w-3xl text-sm leading-6 text-slate-300 light:text-slate-600">{callback.notes}</p>}
                  </div>
                  <div className="flex flex-col gap-3 lg:min-w-[240px] lg:items-end">
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-right light:border-slate-200 light:bg-slate-50">
                      <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Scheduled for</p>
                      <p className="mt-2 text-sm font-medium text-white light:text-slate-900">{formatDateTime(callback.scheduled_at)}</p>
                      <p className={`mt-1 text-xs ${isOverdue ? 'text-rose-400' : 'text-slate-400'}`}>{formatRelativeTime(callback.scheduled_at)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => markDone(callback.id)}
                      className="inline-flex items-center justify-center rounded-2xl border border-[#7C3AED]/30 bg-[#7C3AED]/15 px-4 py-2 text-sm font-medium text-violet-200 transition hover:border-[#7C3AED]/60 hover:bg-[#7C3AED]/25 light:text-violet-700 light:hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
                      aria-label={`Mark callback for ${callback.parent_name} as done`}
                    >
                      Mark as done
                    </button>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 px-6 py-14 text-center text-sm text-slate-400 light:border-slate-200 light:bg-slate-50 light:text-slate-500">
              No pending callbacks. Everything in the queue has been cleared for now.
            </div>
          )}
        </div>
      </PanelCard>
    </div>
  );
}
