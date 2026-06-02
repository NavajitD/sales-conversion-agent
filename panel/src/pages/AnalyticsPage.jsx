import { BarChart3, CheckCircle2, Clock3, Percent, XCircle } from 'lucide-react';
import ErrorState from '../components/ErrorState';
import HorizontalBarChart from '../components/HorizontalBarChart';
import LoadingState from '../components/LoadingState';
import PanelCard from '../components/PanelCard';
import SentimentTrendChart from '../components/SentimentTrendChart';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { useApi } from '../hooks/useApi';
import { formatConversionRate, formatDuration, titleize } from '../lib/utils';

const INTENT_COLORS = {
  hard_no: 'bg-rose-500',
  soft_no: 'bg-amber-400',
  positive: 'bg-emerald-400',
  ambiguous: 'bg-sky-400',
};

const INTENT_TONES = {
  hard_no: 'error',
  soft_no: 'warning',
  positive: 'success',
  ambiguous: 'info',
};

export default function AnalyticsPage() {
  const { data, loading, error, refetch } = useApi('/api/dashboard/analytics', {
    initialData: {
      total_calls: 0,
      completed_calls: 0,
      conversion_rate: 0,
      avg_duration_seconds: 0,
      outcomes: [],
      top_objections: [],
      top_strategies: [],
      sentiment_trend: [],
      intent_breakdown: [],
      rejection_reasons: [],
      final_sentiments: [],
    },
  });

  if (loading) return <LoadingState label="Loading analytics" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  const hardNos = (data.intent_breakdown ?? []).find((i) => i.intent_classification === 'hard_no')?.n ?? 0;
  const softNos = (data.intent_breakdown ?? []).find((i) => i.intent_classification === 'soft_no')?.n ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={BarChart3} label="Total calls" value={data.total_calls ?? 0} hint="All attempts tracked by the voice agent" />
        <StatCard icon={CheckCircle2} label="Completed calls" value={data.completed_calls ?? 0} hint="Calls with finalised outcomes" />
        <StatCard icon={Percent} label="Conversion rate" value={formatConversionRate(data.conversion_rate)} hint="Enrollment and win-rate snapshot" />
        <StatCard icon={Clock3} label="Avg duration" value={formatDuration(data.avg_duration_seconds)} hint="Average time spent per conversation" />
      </div>

      {/* Hard No vs Soft No breakdown */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <PanelCard title="Intent classification" subtitle="Hard No vs Soft No vs Positive signal distribution">
          <div className="space-y-3">
            {(data.intent_breakdown ?? []).map((item) => {
              const total = (data.intent_breakdown ?? []).reduce((s, i) => s + i.n, 0);
              const pct = total > 0 ? ((item.n / total) * 100).toFixed(1) : 0;
              return (
                <div key={item.intent_classification} className="flex items-center gap-3">
                  <StatusBadge tone={INTENT_TONES[item.intent_classification] || 'muted'}>
                    {titleize(item.intent_classification)}
                  </StatusBadge>
                  <div className="flex-1">
                    <div className="h-2 rounded-full bg-slate-800">
                      <div
                        className={`h-2 rounded-full ${INTENT_COLORS[item.intent_classification] || 'bg-slate-500'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                  <span className="min-w-[3rem] text-right text-xs text-slate-400">{item.n} ({pct}%)</span>
                </div>
              );
            })}
            {!(data.intent_breakdown ?? []).length && (
              <p className="text-sm text-slate-500">No intent data yet.</p>
            )}
          </div>
        </PanelCard>

        <PanelCard title="Rejection reasons" subtitle="Why parents say no — objection breakdown for Hard No & Soft No">
          <div className="space-y-2">
            {(data.rejection_reasons ?? []).map((item, idx) => (
              <div key={idx} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2">
                <div className="flex items-center gap-2">
                  <XCircle className={`h-3.5 w-3.5 ${item.intent_classification === 'hard_no' ? 'text-rose-400' : 'text-amber-400'}`} />
                  <span className="text-sm text-slate-200">{titleize(item.objection_primary)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge tone={item.intent_classification === 'hard_no' ? 'error' : 'warning'}>
                    {item.intent_classification === 'hard_no' ? 'Hard No' : 'Soft No'}
                  </StatusBadge>
                  <span className="text-xs font-medium text-slate-400">{item.n}×</span>
                </div>
              </div>
            ))}
            {!(data.rejection_reasons ?? []).length && (
              <p className="text-sm text-slate-500">No rejection data yet.</p>
            )}
          </div>
        </PanelCard>

        <PanelCard title="Hard No vs Soft No" subtitle="Rejection severity — can we save the lead?">
          <div className="flex items-end justify-center gap-8 py-4">
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-32 w-16 items-end rounded-xl border border-slate-800 bg-slate-950/70">
                <div
                  className="w-full rounded-b-xl bg-rose-500"
                  style={{ height: `${Math.min(100, (hardNos / Math.max(hardNos + softNos, 1)) * 100)}%` }}
                />
              </div>
              <span className="text-lg font-bold text-rose-400">{hardNos}</span>
              <span className="text-xs text-slate-500">Hard No</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-32 w-16 items-end rounded-xl border border-slate-800 bg-slate-950/70">
                <div
                  className="w-full rounded-b-xl bg-amber-400"
                  style={{ height: `${Math.min(100, (softNos / Math.max(hardNos + softNos, 1)) * 100)}%` }}
                />
              </div>
              <span className="text-lg font-bold text-amber-400">{softNos}</span>
              <span className="text-xs text-slate-500">Soft No</span>
            </div>
          </div>
          <p className="text-center text-xs text-slate-500">
            {softNos > 0 ? `${((softNos / Math.max(hardNos + softNos, 1)) * 100).toFixed(0)}% of rejections are soft — winnable with follow-up` : 'No rejection data yet'}
          </p>
        </PanelCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <HorizontalBarChart
          title="Top objections"
          subtitle="Most frequent blockers raised by parents."
          items={data.top_objections ?? []}
          getLabel={(item) => titleize(item.objection_primary, 'Unknown objection')}
          barClassName="bg-amber-400"
        />
        <HorizontalBarChart
          title="Top strategies"
          subtitle="Counseling approaches applied by the voice agent."
          items={data.top_strategies ?? []}
          getLabel={(item) => titleize(item.strategy_applied, 'Unknown strategy')}
          barClassName="bg-sky-400"
        />
        <HorizontalBarChart
          title="Outcome distribution"
          subtitle="Next-step outcomes across the conversion funnel."
          items={data.outcomes ?? []}
          getLabel={(item) => titleize(item.next_step, 'Pending')}
          barClassName="bg-[#7C3AED]"
        />
        <SentimentTrendChart
          title="Sentiment trend"
          subtitle="Recent call endings mapped across the sentiment scale."
          items={data.sentiment_trend ?? []}
        />
      </div>
    </div>
  );
}
