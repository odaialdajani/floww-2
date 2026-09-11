import { useCallback, useRef, useState } from "react";

// A reply belongs to the selection which requested it, including after a
// failed ticker change or a late manual refresh.
export function useScopedReading(scope) {
  const current = useRef({ scope });
  if (current.current.scope !== scope) current.current = { scope };
  const request = current.current;
  const [saved, setSaved] = useState(null);
  const save = useCallback((value) => {
    if (current.current === request) setSaved({ request, value });
  }, [request]);
  return [saved?.request === request ? saved.value : null, save];
}
