import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";

/**
 * useReviewJournal — shared review-journal fetch/save for a snapshot.
 * Same endpoints + frozen-context semantics as the Solstice drawer; extracted
 * so Triad reuses the journal without duplicating the request logic.
 * Read-only controls never touch brokerage routes (POST goes to the review
 * journal, which persists research rows, not orders).
 */
export function useReviewJournal(ticker, snapshotId, contextNote) {
  const [reviewState, setReviewState] = useState(null);
  const [reviewDec, setReviewDec] = useState(null);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [reviewReason, setReviewReason] = useState("");
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!ticker || !snapshotId) {
      setReviewState(null);
      setReviewDec(null);
      setReviewQueue([]);
      setReviewLoading(false);
      return undefined;
    }
    let cancelled = false;
    setReviewState(null);
    setReviewDec(null);
    setReviewQueue([]);
    setReviewLoading(true);
    axios
      .get(`${BACKEND_API}/solstice/${encodeURIComponent(ticker)}/decisions`, { timeout: 15000 })
      .then((r) => {
        if (cancelled) return;
        const list = r?.data?.decisions || [];
        const dec = list.find((d) => d.snapshot_id === snapshotId) || null;
        const queue = list
          .filter((d) => !d.review_state && d.snapshot_id !== snapshotId)
          .sort((a, b) => (String(b.at_ts || "") < String(a.at_ts || "") ? -1 : 1))
          .slice(0, 5);
        setReviewDec(dec);
        setReviewState(dec ? dec.review_state : null);
        setReviewQueue(queue);
      })
      .catch(() => { /* journal not yet populated — leave null */ })
      .finally(() => { if (!cancelled) setReviewLoading(false); });
    return () => { cancelled = true; };
  }, [ticker, snapshotId, nonce]);

  const saveReview = useCallback((state) => {
    if (!reviewDec?.decision_id || reviewSaving) return;
    setReviewSaving(true);
    axios
      .post(
        `${BACKEND_API}/solstice/${encodeURIComponent(ticker)}/decisions/${encodeURIComponent(reviewDec.decision_id)}/review`,
        { state, reason: reviewReason || null, note: contextNote || null }
      )
      .then(() => setNonce((n) => n + 1))
      .catch(() => { /* save failed — pill keeps prior state, no false durable */ })
      .finally(() => setReviewSaving(false));
  }, [ticker, reviewDec, reviewSaving, reviewReason, contextNote]);

  return {
    reviewState, reviewDec, reviewQueue, reviewReason, setReviewReason,
    reviewSaving, reviewLoading, saveReview,
  };
}
