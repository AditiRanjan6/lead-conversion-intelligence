import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";

interface AdminTokenContextValue {
  token: string;
  setToken: (token: string) => void;
}

const AdminTokenContext = createContext<AdminTokenContextValue | null>(null);

export function AdminTokenProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState("");
  return (
    <AdminTokenContext.Provider value={{ token, setToken }}>
      {children}
    </AdminTokenContext.Provider>
  );
}

export function useAdminToken(): AdminTokenContextValue {
  const context = useContext(AdminTokenContext);
  if (context === null) {
    throw new Error("useAdminToken must be used inside AdminTokenProvider.");
  }
  return context;
}
