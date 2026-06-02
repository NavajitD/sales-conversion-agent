export default function LoadingState({ label = 'Loading dashboard data' }) {
  return (
    <div className="flex min-h-[260px] items-center justify-center rounded-3xl border border-slate-800/80 bg-slate-900/70 px-6 text-center">
      <div className="space-y-3">
        <div className="mx-auto h-3 w-3 animate-pulse rounded-full bg-[#7C3AED]" />
        <p className="text-sm text-slate-300">{label}…</p>
      </div>
    </div>
  );
}
