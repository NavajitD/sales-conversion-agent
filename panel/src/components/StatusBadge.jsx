import { cn } from '../lib/utils';

const toneClasses = {
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 light:text-emerald-700 light:bg-emerald-50 light:border-emerald-200',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-400 light:text-amber-700 light:bg-amber-50 light:border-amber-200',
  danger: 'border-rose-500/30 bg-rose-500/10 text-rose-400 light:text-rose-700 light:bg-rose-50 light:border-rose-200',
  error: 'border-rose-500/30 bg-rose-500/10 text-rose-400 light:text-rose-700 light:bg-rose-50 light:border-rose-200',
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-300 light:text-sky-700 light:bg-sky-50 light:border-sky-200',
  purple: 'border-[#7C3AED]/30 bg-[#7C3AED]/15 text-violet-300 light:text-violet-700 light:bg-violet-50 light:border-violet-200',
  neutral: 'border-slate-700 bg-slate-800/90 text-slate-300 light:border-slate-200 light:bg-slate-100 light:text-slate-600',
};

export default function StatusBadge({ children, tone = 'neutral', className }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium tracking-wide',
        toneClasses[tone] ?? toneClasses.neutral,
        className,
      )}
    >
      {children}
    </span>
  );
}
