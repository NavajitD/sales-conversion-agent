import { LoaderCircle } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import TurnTimeline from './TurnTimeline';

export default function CallTurnsPanel({ callId }) {
  const { data, loading, error } = useApi(`/api/dashboard/calls/${callId}/turns`, {
    initialData: { turns: [] },
  });

  if (loading) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-6 text-sm text-slate-300">
        <LoaderCircle className="h-4 w-4 animate-spin text-violet-300" />
        Loading turn-by-turn call details…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 px-4 py-6 text-sm text-rose-200">
        Could not load call turns: {error}
      </div>
    );
  }

  return <TurnTimeline turns={data?.turns ?? []} emptyText="No turn transcript found for this call." />;
}
