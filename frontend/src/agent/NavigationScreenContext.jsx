import { useLayoutEffect, useRef } from "react";
import useScreenContext, { publishScreenContext } from "./useScreenContext";

// Mount this before study children: their checked readings take ownership after
// this page selection. Changing a study must not replace a memoized reading.
export default function NavigationScreenContext({ page, ticker, study }) {
  const [current] = useScreenContext();
  const latest = useRef(current);
  latest.current = current;
  const owner = useRef(Symbol("navigation-screen"));
  const release = useRef(null);
  const selectedTicker = String(ticker || "").trim().replace(/^\^/, "").toUpperCase();
  useLayoutEffect(() => {
    const selected = latest.current;
    const selectedReadingTicker = String(selected.ticker || "").trim().replace(/^\^/, "").toUpperCase();
    if (selected.page === page && selectedReadingTicker === selectedTicker && !selected.navigationOnly) return;
    release.current = publishScreenContext({
      contextVersion: 1, page, ticker: selectedTicker || null, study, navigationOnly: true,
    }, owner.current);
  }, [page, selectedTicker, study]);
  useLayoutEffect(() => () => release.current?.(), []);
  return null;
}
