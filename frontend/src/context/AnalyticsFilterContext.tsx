import { createContext, useContext, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { AnalyticsFilters } from "../types";

interface AnalyticsFilterContextValue {
  filters: AnalyticsFilters;
  setFilters: Dispatch<SetStateAction<AnalyticsFilters>>;
}

const AnalyticsFilterContext =
  createContext<AnalyticsFilterContextValue | null>(null);

export function AnalyticsFilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<AnalyticsFilters>({});

  return (
    <AnalyticsFilterContext.Provider value={{ filters, setFilters }}>
      {children}
    </AnalyticsFilterContext.Provider>
  );
}

export function useAnalyticsFilters(): AnalyticsFilterContextValue {
  const context = useContext(AnalyticsFilterContext);
  if (!context) {
    throw new Error(
      "useAnalyticsFilters must be used within AnalyticsFilterProvider.",
    );
  }
  return context;
}
