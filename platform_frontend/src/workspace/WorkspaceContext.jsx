import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { loadWorkspace } from "./service";

const WorkspaceContext = createContext(null);
export const useWorkspace = () => useContext(WorkspaceContext);
export function WorkspaceProvider({ user, children }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const professor = user.authority_level <= 1;
  const refresh = useCallback(async () => {
    try {
      const next = await loadWorkspace(professor);
      setItems(next);
      setError("");
      return next;
    } catch (error) {
      setError(error.message);
      throw error;
    }
  }, [professor]);
  useEffect(() => {
    let active = true;
    loadWorkspace(professor)
      .then((data) => {
        if (active) setItems(data);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [professor]);
  if (!items)
    return (
      <main className="p-content">
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button onClick={() => refresh().catch(() => {})}>Retry</button>
          </>
        ) : (
          <p role="status">Loading your workspace…</p>
        )}
      </main>
    );
  return (
    <WorkspaceContext.Provider value={{ items, user, professor, refresh }}>
      {error && <p role="alert">{error}</p>}
      {children}
    </WorkspaceContext.Provider>
  );
}
