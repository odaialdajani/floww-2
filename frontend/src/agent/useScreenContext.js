import { useEffect, useState } from "react";

const DEFAULT_CTX = { page: "heatseeker", ticker: "SPY", dte: "all", metric: null, mode: null, expiries: 6, selectedStrike: null, selectedSignal: null };

/** Screen context publishers feed this hook (plan v3 L7). No vision model:
 *  {page, ticker, dte, metric, mode, expiries, selectedStrike, selectedSignal}.
 */
export default function useScreenContext(external) {
  const [ctx, setCtx] = useState(DEFAULT_CTX);
  useEffect(() => {
    if (!external) return;
    setCtx((c) => ({ ...c, ...external }));
  }, [external]);
  useEffect(() => {
    const read = () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const page = params.get("page") || DEFAULT_CTX.page;
        setCtx((c) => ({ ...c, page }));
      } catch {
        /* ignore */
      }
    };
    read();
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, []);
  return [ctx, setCtx];
}
