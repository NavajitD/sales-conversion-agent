import { ChevronDown, ChevronUp, Clock3, PhoneCall, ShieldCheck, TrendingUp } from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import CallTurnsPanel from '../components/CallTurnsPanel';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import PanelCard from '../components/PanelCard';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { useApi } from '../hooks/useApi';
import {
  formatDateTime,
  formatDuration,
  getOutcomeTone,
  getStatusTone,
  sortByDate,
  titleize,
} from '../lib/utils';

export default function CallHistoryPage() {
  const { data, loading, error, refetch } = useApi('/api/dashboard/calls', {
    initialData: { calls: [] },
  });
  const [expandedCallId, setExpandedCallId] = useState(null);

  const calls = useMemo(() => sortByDate(data?.calls ?? [], 'started_at'), [data]);
  const completedCalls = calls.filter((call) => String(call.status || '').toLowerCase() === 'completed').length;
  const avgDuration = calls.length
    ? formatDuration(calls.reduce((sum, call) => sum + Number(call.duration_seconds || 0), 0) / calls.length)
    : '0s';
  const conversionWins = calls.filter((call) => getOutcomeTone(call.next_step) === 'success').length;

  if (loading) return <LoadingState label="Loading call history" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={PhoneCall} label="All calls" value={calls.length} hint="Historical voice attempts recorded in CRM" />
        <StatCard icon={ShieldCheck} label="Completed" value={completedCalls} hint="Calls that reached a final disposition" />
        <StatCard icon={Clock3} label="Avg duration" value={avgDuration} hint="Average talk-time across all attempts" />
        <StatCard icon={TrendingUp} label="Conversion wins" value={conversionWins} hint="Calls ending in enrollment or booked next step" />
      </div>

      <PanelCard title="Call attempt ledger" subtitle="Expand any row to inspect objection handling, strategies and turn-level reasoning.">
        <div className="crm-scrollbar overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800 text-left text-sm light:divide-slate-200">
            <thead>
              <tr className="text-xs uppercase tracking-[0.22em] text-slate-500">
                <th className="px-4 py-3 font-medium">Parent Name</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Duration</th>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Primary Objection</th>
                <th className="px-4 py-3 font-medium">Outcome</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 text-slate-300 light:divide-slate-100 light:text-slate-700">
              {calls.map((call) => {
                const isExpanded = expandedCallId === call.id;
                return (
                  <Fragment key={call.id}>
                    <tr className="transition hover:bg-slate-800/45 light:hover:bg-violet-50/50">
                      <td className="px-4 py-4">
                        <button
                          type="button"
                          onClick={() => setExpandedCallId(isExpanded ? null : call.id)}
                          className="flex items-center gap-3 text-left"
                          aria-expanded={isExpanded}
                          aria-label={`Expand details for ${call.parent_name}`}
                        >
                          <span className="rounded-xl border border-slate-800 bg-slate-950/70 p-2 text-slate-400 light:border-slate-200 light:bg-slate-100 light:text-slate-500">
                            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                          </span>
                          <div>
                            <p className="font-medium text-white light:text-slate-900">{call.parent_name}</p>
                            <p className="text-xs text-slate-500">Demo #{call.demo_id ?? '—'}</p>
                          </div>
                        </button>
                      </td>
                      <td className="px-4 py-4">{call.phone || '—'}</td>
                      <td className="px-4 py-4">
                        <StatusBadge tone={getStatusTone(call.status)}>{titleize(call.status)}</StatusBadge>
                      </td>
                      <td className="px-4 py-4">{formatDuration(call.duration_seconds)}</td>
                      <td className="px-4 py-4">{formatDateTime(call.started_at)}</td>
                      <td className="px-4 py-4">{call.objection_primary ? titleize(call.objection_primary) : '—'}</td>
                      <td className="px-4 py-4">
                        <StatusBadge tone={getOutcomeTone(call.next_step)}>{titleize(call.next_step, 'Pending')}</StatusBadge>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-slate-950/40 light:bg-slate-50">
                        <td className="px-4 pb-5 pt-1" colSpan={7}>
                          <div className="rounded-3xl border border-slate-800/80 bg-slate-900/60 p-4 light:border-slate-200 light:bg-white">
                            <div className="mb-4 flex flex-wrap gap-2">
                              {call.objection_primary && <StatusBadge tone="warning">Primary objection: {titleize(call.objection_primary)}</StatusBadge>}
                              {call.intent_final && <StatusBadge tone="info">Final intent: {titleize(call.intent_final)}</StatusBadge>}
                              {call.next_step && <StatusBadge tone={getOutcomeTone(call.next_step)}>Outcome: {titleize(call.next_step)}</StatusBadge>}
                            </div>
                            <CallTurnsPanel callId={call.id} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </PanelCard>
    </div>
  );
}
