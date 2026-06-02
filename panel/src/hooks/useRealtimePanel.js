import { useEffect, useMemo, useRef, useState } from 'react';

const getSocketUrl = () => {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/panel`;
};

const normalisePayload = (message) => {
  const firstPass = message?.payload ?? message?.data ?? message;
  return firstPass?.payload ?? firstPass;
};

const resolveCallId = (payload, activeCalls) => {
  const candidates = [payload?.call_attempt_id, payload?.call_id, payload?.callId, payload?.id];
  const matchedId = candidates.find((candidate) => candidate !== undefined && candidate !== null && candidate !== '');
  if (matchedId) return String(matchedId);

  const parentId = payload?.parent_id ?? payload?.parentId;
  if (parentId !== undefined && parentId !== null) {
    const matchedCall = activeCalls.find((call) => String(call.parent_id) === String(parentId));
    if (matchedCall) return String(matchedCall.id);
  }

  if (activeCalls.length === 1) return String(activeCalls[0].id);
  return null;
};

const normaliseTurn = (message, payload, callId) => ({
  id:
    payload?.id ??
    `${callId}-${payload?.ts ?? payload?.timestamp ?? payload?.started_at ?? Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`,
  call_attempt_id: payload?.call_attempt_id ?? callId,
  ts: payload?.ts ?? payload?.timestamp ?? payload?.started_at ?? new Date().toISOString(),
  utterance: payload?.utterance ?? payload?.transcript ?? payload?.message ?? 'Live update received',
  intent_classification: payload?.intent_classification ?? payload?.intent ?? message?.type ?? payload?.event_type,
  intent_confidence: payload?.intent_confidence,
  objection_primary: payload?.objection_primary,
  objection_secondary: payload?.objection_secondary,
  strategy_applied: payload?.strategy_applied ?? payload?.strategy,
  sentiment: payload?.sentiment ?? payload?.sentiment_end,
  is_final: payload?.is_final ?? payload?.final ?? false,
  next_step_label: payload?.next_step_label ?? payload?.next_step,
  counselor_notes: payload?.counselor_notes ?? payload?.reasoning ?? payload?.summary ?? payload?.notes,
  status: payload?.status ?? message?.status,
});

export function useRealtimePanel(activeCalls = []) {
  const activeCallsRef = useRef(activeCalls);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [eventsByCall, setEventsByCall] = useState({});

  useEffect(() => {
    activeCallsRef.current = activeCalls;
  }, [activeCalls]);

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setConnectionStatus((current) => (current === 'live' ? current : 'connecting'));

      socket = new WebSocket(getSocketUrl());

      socket.onopen = () => {
        setConnectionStatus('live');
      };

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          const payload = normalisePayload(message);
          const callId = resolveCallId(payload, activeCallsRef.current);
          if (!callId) return;

          const turn = normaliseTurn(message, payload, callId);
          setEventsByCall((current) => {
            const existing = current[callId] ?? [];
            return {
              ...current,
              [callId]: [...existing, turn].slice(-120),
            };
          });
        } catch (parseError) {
          console.warn('Unable to parse live panel event', parseError);
        }
      };

      socket.onerror = () => {
        setConnectionStatus('error');
      };

      socket.onclose = () => {
        if (disposed) return;
        setConnectionStatus('reconnecting');
        reconnectTimer = window.setTimeout(connect, 2500);
      };
    };

    connect();

    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  const totalEvents = useMemo(
    () => Object.values(eventsByCall).reduce((total, items) => total + items.length, 0),
    [eventsByCall],
  );

  return {
    connectionStatus,
    eventsByCall,
    totalEvents,
  };
}
