import { AlertCircle } from 'lucide-react';
import PanelCard from './PanelCard';

export default function ErrorState({ message, onRetry }) {
  return (
    <PanelCard title="Unable to load data" subtitle={message || 'Please try again.'}>
      <div className="flex flex-col gap-4 rounded-2xl border border-rose-500/20 bg-rose-500/5 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3 text-rose-200">
          <AlertCircle className="mt-0.5 h-5 w-5" />
          <p className="text-sm">The CRM could not reach the backend service.</p>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center justify-center rounded-2xl border border-[#7C3AED]/30 bg-[#7C3AED]/15 px-4 py-2 text-sm font-medium text-violet-200 transition hover:border-[#7C3AED]/60 hover:bg-[#7C3AED]/25"
          >
            Retry
          </button>
        )}
      </div>
    </PanelCard>
  );
}
