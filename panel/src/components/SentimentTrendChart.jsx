import PanelCard from './PanelCard';
import { formatShortDate, formatTime, getSentimentScore, getSentimentTone, titleize } from '../lib/utils';

const toneToColor = {
  success: 'bg-emerald-400',
  warning: 'bg-amber-400',
  danger: 'bg-rose-400',
  neutral: 'bg-slate-400',
};

export default function SentimentTrendChart({ title, subtitle, items = [] }) {
  return (
    <PanelCard title={title} subtitle={subtitle}>
      {items.length ? (
        <div className="space-y-6">
          <div className="flex h-56 items-end gap-3 overflow-x-auto pb-2">
            {items.map((item, index) => {
              const score = getSentimentScore(item.sentiment_end);
              const tone = getSentimentTone(item.sentiment_end);

              return (
                <div key={`${item.id ?? index}-${item.started_at}`} className="flex min-w-[64px] flex-1 flex-col items-center gap-3">
                  <div className="relative flex h-40 w-full items-end rounded-2xl bg-slate-950/80 p-2 light:bg-slate-100">
                    <div
                      className={`w-full rounded-xl ${toneToColor[tone] ?? toneToColor.neutral}`}
                      style={{ height: `${Math.max((score / 4) * 100, 15)}%` }}
                      title={`${titleize(item.sentiment_end)} • ${formatTime(item.started_at)}`}
                    />
                  </div>
                  <div className="text-center text-[11px] text-slate-400 light:text-slate-500">
                    <p>{formatShortDate(item.started_at)}</p>
                    <p>{formatTime(item.started_at)}</p>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {items.slice(0, 4).map((item, index) => (
              <div key={`${item.id ?? index}-legend`} className="rounded-2xl border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-300 light:border-slate-200 light:bg-slate-50 light:text-slate-600">
                <p className="font-medium text-white light:text-slate-900">{titleize(item.sentiment_end)}</p>
                <p className="mt-1 text-xs text-slate-400 light:text-slate-500">{formatShortDate(item.started_at)} · {formatTime(item.started_at)}</p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-400 light:border-slate-200 light:text-slate-500">
          No sentiment trend available.
        </div>
      )}
    </PanelCard>
  );
}
