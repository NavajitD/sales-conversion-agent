import { cn } from '../lib/utils';

export default function PanelCard({ title, subtitle, action, className, children }) {
  return (
    <section
      className={cn(
        'rounded-3xl border p-5 backdrop-blur-sm',
        'border-slate-800/80 bg-slate-900/70 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.9)]',
        'light:border-slate-200 light:bg-white light:shadow-sm',
        className,
      )}
    >
      {(title || subtitle || action) && (
        <div className="mb-5 flex flex-col gap-3 border-b border-slate-800/80 pb-4 light:border-slate-100 sm:flex-row sm:items-start sm:justify-between">
          <div>
            {title && <h2 className="text-lg font-semibold text-white light:text-slate-900">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm text-slate-400 light:text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
