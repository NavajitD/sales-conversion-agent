import { useCallback, useEffect, useState } from 'react';

export function useApi(path, { initialData = null, refreshInterval = 0 } = {}) {
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setError('');
      const response = await fetch(path);
      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const json = await response.json();
      setData(json);
      setLastUpdated(new Date().toISOString());
    } catch (fetchError) {
      setError(fetchError.message || 'Unable to load data');
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    let isMounted = true;
    let intervalId;

    const load = async () => {
      if (!isMounted) return;
      await fetchData();
    };

    load();

    if (refreshInterval > 0) {
      intervalId = window.setInterval(load, refreshInterval);
    }

    return () => {
      isMounted = false;
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [fetchData, refreshInterval]);

  return {
    data,
    loading,
    error,
    refetch: fetchData,
    lastUpdated,
  };
}
