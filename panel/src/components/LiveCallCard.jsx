import { Clock3, Headphones, Heart, PhoneCall } from 'lucide-react';
import PanelCard from './PanelCard';
import StatusBadge from './StatusBadge';
import TurnTimeline from './TurnTimeline';
import { formatDateTime, formatDuration, getInitials, getOutcomeTone, getSentimentTone, titleize } from '../lib/utils';

const getLiveDuration = (startedAt) => {
  if (!startedAt) return '0s';
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) return '0s';
  return formatDuration(Math.max(0, Math.round((Date.now() - started) / 1000)));
};

const SummaryItem = ({ icon: Icon, label, value, toneClass = 'text-slate-100 light:text-slate-800' }) => (
  <div className="rounded-2xl border border-slate-800/80 bg-slate-950/70 p-4 light:border-slate-200 light:bg-slate-50">
    <div className="flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-500">
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </div>
    <p className={`mt-3 text-sm font-medium ${toneClass}`}>{value}</p>
  </div>
);

export default function LiveCallCard({ call, events = [] }) {
  const latestEvent = events[events.length - 1];
  const latestSentiment = latestEvent?.sentiment ?? latestEvent?.sentiment_end;
  const latestNextStep = latestEvent?.next_step_label ?? latestEvent?.next_step;

  return (
    <PanelCard className="overflow-hidden">
      <div className="grid gap-6 xl:grid-cols-[320px,1fr]">
        <div className="space-y-5">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[#7C3AED]/20 bg-[#7C3AED]/15 text-lg font-semibold text-violet-200">
              {getInitials(call.parent_name)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-xl font-semibold text-white light:text-slate-900">{call.parent_name}</h3>
                <span className="inline-flex h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-400" />
                <StatusBadge tone="success">Live</StatusBadge>
              </div>
              <p className="mt-1 text-sm text-slate-400 light:text-slate-500">{call.phone}</p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <SummaryItem icon={PhoneCall} label="Status" value={titleize(call.status)} />
            <SummaryItem icon={Clock3} label="Started at" value={formatDateTime(call.started_at)} />
            <SummaryItem icon={Headphones} label="Live duration" value={getLiveDuration(call.started_at)} />
            <SummaryItem
              icon={Heart}
              label="Latest sentiment"
              value={latestSentiment ? titleize(latestSentiment) : 'Waiting for reasoning'}
              toneClass={latestSentiment ? (getSentimentTone(latestSentiment) === 'success' ? 'text-emerald-300' : getSentimentTone(latestSentiment) === 'danger' ? 'text-rose-300' : 'text-amber-300') : 'text-slate-300'}
            />
          </div>

          <div className="rounded-2xl border border-[#7C3AED]/20 bg-[#7C3AED]/10 p-4">
            <div className="flex flex-wrap gap-2">
              <StatusBadge tone="purple">{latestEvent?.strategy_applied ? `Strategy: ${titleize(latestEvent.strategy_applied)}` : 'Strategy pending'}</StatusBadge>
              {latestNextStep && <StatusBadge tone={getOutcomeTone(latestNextStep)}>Next: {titleize(latestNextStep)}</StatusBadge>}
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-300 light:text-slate-600">
              {latestEvent?.counselor_notes || 'The reasoning panel will populate as soon as live turns stream in from the voice agent.'}
            </p>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-800/80 bg-slate-950/70 p-4 light:border-slate-200 light:bg-slate-50">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h4 className="text-base font-semibold text-white light:text-slate-900">Reasoning panel</h4>
              <p className="text-sm text-slate-400 light:text-slate-500">Turn-by-turn transcript, objections, strategy and sentiment.</p>
            </div>
            <StatusBadge tone="info">{events.length} live updates</StatusBadge>
          </div>
          <div className="crm-scrollbar max-h-[440px] overflow-y-auto pr-1">
            <TurnTimeline turns={events} emptyText="Waiting for the next live turn…" />
          </div>
        </div>
      </div>
    </PanelCard>
  );
}
