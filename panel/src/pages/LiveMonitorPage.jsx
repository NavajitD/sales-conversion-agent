import { Activity, BarChart3, CheckCircle2, Clock3, Percent, Radio, Wifi } from 'lucide-react';
import { useState } from 'react';
import ErrorState from '../components/ErrorState';
import HorizontalBarChart from '../components/HorizontalBarChart';
import LiveCallPopup from '../components/LiveCallPopup';
import LoadingState from '../components/LoadingState';
import PanelCard from '../components/PanelCard';
import SentimentTrendChart from '../components/SentimentTrendChart';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { useApi } from '../hooks/useApi';
import { useRealtimePanel } from '../hooks/useRealtimePanel';
import { cn, formatConversionRate, formatDuration, getOutcomeTone, getSentimentTone, sortByDate, titleize } from '../lib/utils';

const INTENT_COLORS = {
  hard_no: 'bg-rose-500',
  soft_no: 'bg-amber-400',
  positive: 'bg-emerald-400',
  ambiguous: 'bg-sky-400',
};

export default function LiveMonitorPage() {
  const [selectedCall, setSelectedCall] = useState(null);
  const { data: liveData, loading: liveLoading } = useApi('/api/dashboard/live', {
    initialData: { active_calls: [] },
    refreshInterval: 10000,
  });
  const { data: analyticsData, loading: analyticsLoading, error, refetch } = useApi('/api/dashboard/analytics', {
    initialData: {
      total_calls: 0, completed_calls: 0, conversion_rate: 0, avg_duration_seconds: 0,
      outcomes: [], top_objections: [], top_strategies: [], sentiment_trend: [],
      intent_breakdown: [], rejection_reasons: [], final_sentiments: [],
    },
  });

  const activeCalls = sortByDate(liveData?.active_calls ?? [], 'started_at');
  const { connectionStatus, eventsByCall, totalEvents } = useRealtimePanel(activeCalls);
  const data = analyticsData;

  if (analyticsLoading && liveLoading) return <LoadingState label="Loading command center" aria-busy="true" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  // Build active call status strip from latest events
  const activeCallStatuses = activeCalls.map((call) => {
    const events = eventsByCall[String(call.id)] ?? [];
    const latest = events[events.length - 1];
    return {
      id: call.id,
      name: call.parent_name,
      sentiment: latest?.sentiment ?? latest?.sentiment_end ?? null,
      confidence: latest?.intent_confidence ?? null,
      outcome: latest?.next_step_label ?? latest?.next_step ?? null,
      strategy: latest?.strategy_applied ?? null,
    };
  });

  const hardNos = (data.intent_breakdown ?? []).find((i) => i.intent_classification === 'hard_no')?.n ?? 0;
  const softNos = (data.intent_breakdown ?? []).find((i) => i.intent_classification === 'soft_no')?.n ?? 0;

  return (
    <div className="space-y-6">
      {/* Active calls status bar */}
      {activeCalls.length > 0 && (
        <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 light:border-emerald-200 light:bg-emerald-50/80" role="status" aria-live="polite">
          <div className="mb-2 flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" />
            <span className="text-sm font-semibold text-emerald-300 light:text-emerald-800">{activeCalls.length} active {activeCalls.length === 1 ? 'call' : 'calls'}</span>
            <StatusBadge tone="success">{titleize(connectionStatus)}</StatusBadge>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {activeCallStatuses.map((call) => (
              <button
                key={call.id}
                onClick={() => setSelectedCall(call)}
                className="flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-slate-900/60 px-3 py-2 text-left transition hover:border-emerald-400/40 hover:bg-slate-800/80 light:border-emerald-100 light:bg-white light:hover:border-emerald-300 light:hover:bg-emerald-50"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-white light:text-slate-900">{call.name}</p>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {call.sentiment && <StatusBadge tone={getSentimentTone(call.sentiment)}>{titleize(call.sentiment)}</StatusBadge>}
                    {call.confidence != null && <span className="text-xs text-slate-400 light:text-slate-500">{(call.confidence * 100).toFixed(0)}% conf.</span>}
                    {call.outcome && <StatusBadge tone={getOutcomeTone(call.outcome)}>{titleize(call.outcome)}</StatusBadge>}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* No active calls — subtle indicator */}
      {activeCalls.length === 0 && (
        <div className="flex items-center gap-3 rounded-2xl border border-slate-800/80 bg-slate-900/60 px-4 py-3 light:border-slate-200 light:bg-slate-50" role="status">
          <Radio className="h-4 w-4 text-slate-400" />
          <span className="text-sm text-slate-400 light:text-slate-500">No active calls — standing by</span>
          <StatusBadge tone={connectionStatus === 'live' ? 'success' : 'neutral'}>{titleize(connectionStatus)}</StatusBadge>
        </div>
      )}

      {/* Analytics stat cards */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={BarChart3} label="Total calls" value={data.total_calls ?? 0} hint="All attempts tracked" />
        <StatCard icon={CheckCircle2} label="Completed" value={data.completed_calls ?? 0} hint="Calls with final outcomes" />
        <StatCard icon={Percent} label="Conversion rate" value={formatConversionRate(data.conversion_rate)} hint="Enrollment win-rate" />
        <StatCard icon={Clock3} label="Avg duration" value={formatDuration(data.avg_duration_seconds)} hint="Average per conversation" />
      </div>

      {/* Intent + Rejection breakdown */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <PanelCard title="Intent classification" subtitle="Hard No vs Soft No vs Positive">
          <div className="space-y-3">
            {(data.intent_breakdown ?? []).map((item) => {
              const total = (data.intent_breakdown ?? []).reduce((s, i) => s + i.n, 0);
              const pct = total > 0 ? ((item.n / total) * 100).toFixed(1) : 0;
              return (
                <div key={item.intent_classification} className="flex items-center gap-3">
                  <StatusBadge tone={item.intent_classification === 'hard_no' ? 'danger' : item.intent_classification === 'soft_no' ? 'warning' : 'success'}>
                    {titleize(item.intent_classification)}
                  </StatusBadge>
                  <div className="flex-1">
                    <div className="h-2 rounded-full bg-slate-800 light:bg-slate-200">
                      <div className={`h-2 rounded-full ${INTENT_COLORS[item.intent_classification] || 'bg-slate-400'}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                  <span className="min-w-[3rem] text-right text-xs text-slate-500">{item.n} ({pct}%)</span>
                </div>
              );
            })}
            {!(data.intent_breakdown ?? []).length && <p className="text-sm text-slate-500">No intent data yet.</p>}
          </div>
        </PanelCard>

        <PanelCard title="Rejection reasons" subtitle="Why parents decline">
          <div className="space-y-2">
            {(data.rejection_reasons ?? []).map((item, idx) => (
              <div key={idx} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2 light:border-slate-100 light:bg-slate-50">
                <span className="text-sm text-slate-200 light:text-slate-700">{titleize(item.objection_primary)}</span>
                <div className="flex items-center gap-2">
                  <StatusBadge tone={item.intent_classification === 'hard_no' ? 'danger' : 'warning'}>
                    {item.intent_classification === 'hard_no' ? 'Hard' : 'Soft'}
                  </StatusBadge>
                  <span className="text-xs font-medium text-slate-500">{item.n}×</span>
                </div>
              </div>
            ))}
            {!(data.rejection_reasons ?? []).length && <p className="text-sm text-slate-500">No rejection data yet.</p>}
          </div>
        </PanelCard>

        <PanelCard title="Hard No vs Soft No" subtitle="Rejection severity">
          <div className="flex items-end justify-center gap-8 py-4">
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-28 w-14 items-end rounded-xl border border-slate-800 bg-slate-950/70 light:border-slate-200 light:bg-slate-50">
                <div className="w-full rounded-b-xl bg-rose-500" style={{ height: `${Math.min(100, (hardNos / Math.max(hardNos + softNos, 1)) * 100)}%` }} />
              </div>
              <span className="text-lg font-bold text-rose-500">{hardNos}</span>
              <span className="text-xs text-slate-500">Hard No</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-28 w-14 items-end rounded-xl border border-slate-800 bg-slate-950/70 light:border-slate-200 light:bg-slate-50">
                <div className="w-full rounded-b-xl bg-amber-400" style={{ height: `${Math.min(100, (softNos / Math.max(hardNos + softNos, 1)) * 100)}%` }} />
              </div>
              <span className="text-lg font-bold text-amber-500">{softNos}</span>
              <span className="text-xs text-slate-500">Soft No</span>
            </div>
          </div>
          <p className="text-center text-xs text-slate-500">
            {softNos > 0 ? `${((softNos / Math.max(hardNos + softNos, 1)) * 100).toFixed(0)}% of rejections are soft — winnable` : 'No data yet'}
          </p>
        </PanelCard>
      </div>

      {/* Charts */}
      <div className="grid gap-6 xl:grid-cols-2">
        <HorizontalBarChart title="Top objections" subtitle="Frequent parent blockers" items={data.top_objections ?? []} getLabel={(item) => titleize(item.objection_primary, 'Unknown')} barClassName="bg-amber-400" />
        <HorizontalBarChart title="Top strategies" subtitle="Agent approaches applied" items={data.top_strategies ?? []} getLabel={(item) => titleize(item.strategy_applied, 'Unknown')} barClassName="bg-sky-400" />
        <HorizontalBarChart title="Outcome distribution" subtitle="Conversion funnel outcomes" items={data.outcomes ?? []} getLabel={(item) => titleize(item.next_step, 'Pending')} barClassName="bg-[#7C3AED]" />
        <SentimentTrendChart title="Sentiment trend" subtitle="Recent call sentiment endings" items={data.sentiment_trend ?? []} />
      </div>

      {selectedCall && (
        <LiveCallPopup
          parentName={selectedCall.name}
          callAttemptId={selectedCall.id}
          onClose={() => setSelectedCall(null)}
        />
      )}
    </div>
  );
}
