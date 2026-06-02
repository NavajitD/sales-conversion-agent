import { ArrowUpRight } from 'lucide-react';
import { cn } from '../lib/utils';

export default function StatCard({ icon: Icon, label, value, hint, className }) {
  return (
    <div
      className={cn(
        'rounded-3xl border p-5',
        'border-slate-800/80 bg-slate-900/75 shadow-[0_20px_70px_-35px_rgba(124,58,237,0.55)]',
        'light:border-slate-200 light:bg-white light:shadow-sm',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-400 light:text-slate-500">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-white light:text-slate-900">{value}</p>
        </div>
        {Icon && (
          <div className="rounded-2xl border border-[#7C3AED]/20 bg-[#7C3AED]/15 p-3 text-violet-200 light:text-violet-600">
            <Icon className="h-5 w-5" />
          </div>
        )}
      </div>
      {hint && (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-400 light:text-slate-500">
          <ArrowUpRight className="h-4 w-4 text-violet-300 light:text-violet-500" />
          <span>{hint}</span>
        </div>
      )}
    </div>
  );
}
