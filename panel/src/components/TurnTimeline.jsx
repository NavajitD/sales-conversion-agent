import StatusBadge from './StatusBadge';
import { formatTime, getOutcomeTone, getSentimentTone, titleize } from '../lib/utils';

export default function TurnTimeline({ turns = [], emptyText = 'No turns available yet.' }) {
  if (!turns.length) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-400 light:border-slate-200 light:text-slate-500">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {turns.map((turn, index) => {
        const sentiment = turn.sentiment ?? turn.sentiment_end;
        const nextStep = turn.next_step_label ?? turn.next_step;

        return (
          <div key={turn.id ?? `${turn.ts}-${index}`} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className="mt-1 h-2.5 w-2.5 rounded-full bg-[#7C3AED]" />
              {index !== turns.length - 1 && <div className="mt-2 h-full w-px bg-slate-800 light:bg-slate-200" />}
            </div>
            <div className="flex-1 rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4 light:border-slate-200 light:bg-slate-50">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <p className="text-sm leading-6 text-slate-200 light:text-slate-700">{turn.utterance || 'No transcript captured.'}</p>
                <span className="shrink-0 text-xs text-slate-500">{formatTime(turn.ts)}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {turn.intent_classification && <StatusBadge tone="info">Intent: {titleize(turn.intent_classification)}</StatusBadge>}
                {turn.objection_primary && <StatusBadge tone="warning">Objection: {titleize(turn.objection_primary)}</StatusBadge>}
                {turn.strategy_applied && <StatusBadge tone="purple">Strategy: {titleize(turn.strategy_applied)}</StatusBadge>}
                {sentiment && <StatusBadge tone={getSentimentTone(sentiment)}>Sentiment: {titleize(sentiment)}</StatusBadge>}
                {nextStep && <StatusBadge tone={getOutcomeTone(nextStep)}>Next: {titleize(nextStep)}</StatusBadge>}
                {turn.is_final && <StatusBadge tone="success">Final turn</StatusBadge>}
              </div>
              {turn.counselor_notes && (
                <p className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-300 light:border-slate-200 light:bg-slate-50 light:text-slate-600">
                  {turn.counselor_notes}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
