import PanelCard from './PanelCard';
import { safeNumber } from '../lib/utils';

export default function HorizontalBarChart({
  title,
  subtitle,
  items = [],
  getLabel,
  valueKey = 'n',
  barClassName = 'bg-[#7C3AED]',
}) {
  const maxValue = Math.max(...items.map((item) => safeNumber(item?.[valueKey])), 1);

  return (
    <PanelCard title={title} subtitle={subtitle}>
      {items.length ? (
        <div className="space-y-4">
          {items.map((item, index) => {
            const value = safeNumber(item?.[valueKey]);
            const label = getLabel ? getLabel(item) : item?.label ?? 'Unknown';

            return (
              <div key={`${label}-${index}`} className="space-y-2">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <p className="truncate text-slate-300 light:text-slate-700">{label}</p>
                  <span className="font-medium text-slate-100 light:text-slate-900">{value}</span>
                </div>
                <div className="h-2 rounded-full bg-slate-800 light:bg-slate-200">
                  <div
                    className={`h-2 rounded-full ${barClassName}`}
                    style={{ width: `${Math.max((value / maxValue) * 100, 8)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-400 light:border-slate-200 light:text-slate-500">
          No chart data available yet.
        </div>
      )}
    </PanelCard>
  );
}
