import { useEffect, useState } from "react";
import axios from "axios";
import { fetchFullUniverse } from "./tickerUniverse";

// Keep catalog completeness visible at the caller, including failed later pages.
export default function useTickerDirectory(api) {
  const [tickers, setTickers] = useState(null);
  const [status, setStatus] = useState("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const get = url => axios.get(url, { signal: controller.signal, timeout: 30000 });
    setStatus("loading");
    (async () => {
      let base = null;
      try {
        const response = await get(`${api}/tickers`);
        base = response.data || null;
        if (active && base) setTickers(base);
      } catch (_) { /* Retain the prior list with explicit incomplete status. */ }
      if (!active) return;
      const full = await fetchFullUniverse(get, api);
      if (!active) return;
      if (full.symbols.length) {
        setTickers({ trinity: base?.trinity || [], default: base?.default || [], popular: full.symbols });
      }
      setStatus(!full.complete ? "incomplete" : full.stale ? "saved" : "complete");
    })();
    return () => { active = false; controller.abort(); };
  }, [api, attempt]);
  return { tickers, status, retry: () => setAttempt(value => value + 1) };
}
