export const cn = (...classes) => classes.filter(Boolean).join(' ');

export const safeNumber = (value) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
};

export const formatDateTime = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
};

export const formatTime = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
};

export const formatShortDate = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    month: 'short',
    day: 'numeric',
  }).format(date);
};

export const formatDuration = (value) => {
  const totalSeconds = safeNumber(value);
  if (!totalSeconds) return '0s';

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);

  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
};

export const formatConversionRate = (value) => {
  const numeric = safeNumber(value);
  const normalized = numeric <= 1 ? numeric * 100 : numeric;
  return `${normalized.toFixed(1)}%`;
};

export const titleize = (value, fallback = 'Unknown') => {
  if (!value) return fallback;

  return String(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
};

export const getInitials = (value = 'Parent') =>
  value
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'PA';

export const sortByDate = (items, key, direction = 'desc') =>
  [...items].sort((left, right) => {
    const leftTime = left?.[key] ? new Date(left[key]).getTime() : 0;
    const rightTime = right?.[key] ? new Date(right[key]).getTime() : 0;
    return direction === 'asc' ? leftTime - rightTime : rightTime - leftTime;
  });

export const getOutcomeTone = (value) => {
  const normalized = String(value || '').toLowerCase();

  if (['enrolled', 'converted', 'payment_done', 'second_session_booked'].includes(normalized)) return 'success';
  if (['follow_up', 'followup', 'callback', 'nurture_followup', 'senior_callback', 'interested'].includes(normalized)) return 'warning';
  if (['dropped', 'drop', 'do_not_call', 'not_interested', 'rejected'].includes(normalized)) return 'danger';
  if (['live', 'in_progress', 'ongoing'].includes(normalized)) return 'info';
  return 'neutral';
};

export const getStatusTone = (value) => {
  const normalized = String(value || '').toLowerCase();

  if (['completed', 'done', 'resolved'].includes(normalized)) return 'success';
  if (['queued', 'scheduled', 'pending', 'ringing'].includes(normalized)) return 'warning';
  if (['failed', 'no_answer', 'busy', 'cancelled', 'dropped'].includes(normalized)) return 'danger';
  if (['active', 'live', 'in_progress', 'ongoing'].includes(normalized)) return 'info';
  return 'neutral';
};

export const getSentimentTone = (value) => {
  const normalized = String(value || '').toLowerCase();

  if (['warm', 'positive', 'interested'].includes(normalized)) return 'success';
  if (['neutral', 'mixed'].includes(normalized)) return 'warning';
  if (['cold', 'negative', 'hostile', 'frustrated'].includes(normalized)) return 'danger';
  return 'neutral';
};

export const getSentimentScore = (value) => {
  const normalized = String(value || '').toLowerCase();

  if (['warm', 'positive', 'interested'].includes(normalized)) return 4;
  if (['neutral'].includes(normalized)) return 3;
  if (['mixed', 'cold', 'negative'].includes(normalized)) return 2;
  if (['hostile', 'frustrated'].includes(normalized)) return 1;
  return 2.5;
};

export const getWebSocketTone = (value) => {
  if (value === 'live') return 'success';
  if (value === 'reconnecting' || value === 'connecting') return 'warning';
  if (value === 'error') return 'danger';
  return 'neutral';
};

export const formatRelativeTime = (value) => {
  if (!value) return 'Not scheduled';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not scheduled';

  const diffMinutes = Math.round((date.getTime() - Date.now()) / 60000);
  if (diffMinutes === 0) return 'Now';

  const absMinutes = Math.abs(diffMinutes);
  const hours = Math.floor(absMinutes / 60);
  const minutes = absMinutes % 60;
  const label = hours ? `${hours}h ${minutes}m` : `${minutes}m`;

  return diffMinutes > 0 ? `In ${label}` : `${label} ago`;
};
