import { useEffect, useState } from "react";

export interface ApiResource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useApiResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
): ApiResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    loader(controller.signal)
      .then((result) => {
        setData(result);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            cause instanceof Error ? cause.message : "An unexpected error occurred.",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [loader, reloadKey]);

  return {
    data,
    error,
    loading,
    reload: () => setReloadKey((current) => current + 1),
  };
}
