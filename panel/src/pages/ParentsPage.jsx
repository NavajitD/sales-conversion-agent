import { CalendarClock, Heart, PhoneCall, UserCheck } from 'lucide-react';
import { useCallback, useState } from 'react';
import ErrorState from '../components/ErrorState';
import LiveCallPopup from '../components/LiveCallPopup';
import LoadingState from '../components/LoadingState';
import PanelCard from '../components/PanelCard';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { useApi } from '../hooks/useApi';
import {
  cn,
  formatDateTime,
  getOutcomeTone,
  getSentimentTone,
  getStatusTone,
  sortByDate,
  titleize,
} from '../lib/utils';

export default function ParentsPage() {
  const { data, loading, error, refetch } = useApi('/api/dashboard/parents', {
    initialData: { parents: [] },
  });

  const [callingParentId, setCallingParentId] = useState(null);
  const [activePopup, setActivePopup] = useState(null); // { parentId, parentName, callAttemptId }

  const parents = sortByDate(data?.parents ?? [], 'last_call_at');
  const enrolledCount = parents.filter((parent) => getOutcomeTone(parent.next_step) === 'success').length;
  const followUpCount = parents.filter((parent) => getOutcomeTone(parent.next_step) === 'warning').length;
  const warmCount = parents.filter((parent) => getSentimentTone(parent.sentiment_end) === 'success').length;
  const callbacksScheduled = parents.filter((parent) => parent.next_callback_at).length;

  const handleTriggerCall = useCallback(async (parent) => {
    setCallingParentId(parent.id);
    try {
      const res = await fetch('/api/dashboard/trigger-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_id: parent.id }),
      });
      const json = await res.json();
      if (json.ok) {
        setActivePopup({ parentId: parent.id, parentName: parent.name, callAttemptId: json.attempt_id });
        setTimeout(() => refetch(), 3000);
      }
    } catch (e) { /* ignore */ }
    setCallingParentId(null);
  }, [refetch]);

  if (loading) return <LoadingState label="Loading parent CRM" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={UserCheck} label="Total parents" value={parents.length} hint="Every post-demo lead synced into CRM" />
        <StatCard icon={PhoneCall} label="Follow ups needed" value={followUpCount} hint="Parents still in active nurture" />
        <StatCard icon={Heart} label="Warm sentiment" value={warmCount} hint="Conversations ending with positive intent" />
        <StatCard icon={CalendarClock} label="Callbacks lined up" value={callbacksScheduled} hint="Upcoming commitments needing action" />
      </div>

      <PanelCard title="Parent pipeline" subtitle="Full leads table with call outcomes, callbacks and sentiment health.">
        <div className="mb-4 flex flex-wrap gap-2">
          <StatusBadge tone="success">Enrolled: {enrolledCount}</StatusBadge>
          <StatusBadge tone="warning">Follow up: {followUpCount}</StatusBadge>
          <StatusBadge tone="danger">Dropped: {parents.filter((parent) => getOutcomeTone(parent.next_step) === 'danger').length}</StatusBadge>
        </div>
        <div className="crm-scrollbar overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800/60 text-left text-sm light:divide-slate-200">
            <thead>
              <tr className="text-xs uppercase tracking-[0.22em] text-slate-500">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Child</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Outcome</th>
                <th className="px-4 py-3 font-medium">Sentiment</th>
                <th className="px-4 py-3 font-medium">Callback</th>
                <th className="px-4 py-3 font-medium text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50 text-slate-300 light:divide-slate-100 light:text-slate-700">
              {parents.map((parent) => (
                <tr key={parent.id} className="transition hover:bg-slate-800/30 light:hover:bg-violet-50/50">
                  <td className="px-4 py-4">
                    <div>
                      <p className="font-medium text-white light:text-slate-900">{parent.name}</p>
                      <p className="text-xs text-slate-500">{parent.city || '—'}</p>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-xs font-mono">{parent.phone || '—'}</td>
                  <td className="px-4 py-4">
                    <div>
                      <p>{parent.child_name || '—'}</p>
                      <p className="text-xs text-slate-500">Grade {parent.grade || '—'}</p>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <StatusBadge tone={getStatusTone(parent.last_call_status)}>{titleize(parent.last_call_status)}</StatusBadge>
                  </td>
                  <td className="px-4 py-4">
                    <StatusBadge tone={getOutcomeTone(parent.next_step)}>{titleize(parent.next_step, 'Pending')}</StatusBadge>
                  </td>
                  <td className="px-4 py-4">
                    <StatusBadge tone={getSentimentTone(parent.sentiment_end)}>{titleize(parent.sentiment_end, 'Unknown')}</StatusBadge>
                  </td>
                  <td className="px-4 py-4">
                    <p className="text-xs">{formatDateTime(parent.next_callback_at)}</p>
                  </td>
                  <td className="px-4 py-4 text-center">
                    <button
                      type="button"
                      onClick={() => handleTriggerCall(parent)}
                      disabled={callingParentId === parent.id}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition',
                        'border border-violet-500/80 bg-violet-600 text-white shadow-sm hover:bg-violet-700',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2 light:focus:ring-offset-white',
                      )}
                      aria-label={`Call ${parent.name}`}
                    >
                      <PhoneCall className="h-3.5 w-3.5" />
                      {callingParentId === parent.id ? 'Calling…' : 'Call'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PanelCard>

      {activePopup && (
        <LiveCallPopup
          parentName={activePopup.parentName}
          callAttemptId={activePopup.callAttemptId}
          onClose={() => setActivePopup(null)}
        />
      )}
    </div>
  );
}
