/**
 * RetryButton.jsx
 *
 * Reusable retry button with automatic countdown.
 *
 * Features:
 *   - Shows countdown timer for rate-limit aware retry (HTTP 429)
 *   - Manual retry button for immediate retry
 *   - Different visual states: idle, counting-down, retrying, disabled
 *   - Clear user messaging: "Data source busy. Retrying in 60s..."
 *
 * Props:
 *   {Function} onRetry       - Called when retry is triggered (manual or auto)
 *   {number}  [initialDelay=60]  - Initial countdown delay in seconds
 *   {string}  [message]      - Custom message (default: "Data source busy.")
 *   {string}  [errorCode]    - HTTP error code for display ('429' | '500' | 'network')
 *   {boolean} [autoRetry=true] - Whether to auto-retry after countdown
 *   {string}  [size='sm']    - Size variant: 'xs' | 'sm' | 'md'
 */
import React, { useState, useEffect, useRef, useCallback, memo } from "react";

const SIZE_MAP = {
  xs: "text-[9px] px-2 py-0.5",
  sm: "text-[11px] px-3 py-1",
  md: "text-[13px] px-4 py-1.5",
};

/**
 * Get a user-friendly message based on error type.
 */
function _getMessage(errorCode, customMessage) {
  if (customMessage) return customMessage;
  switch (errorCode) {
    case "404":
      return "No options data for this ticker.";
    case "429":
      return "Data source is rate-limited.";
    case "500":
      return "Server error. Data source may be down.";
    case "network":
      return "Network error. Check your connection.";
    case "timeout":
      return "Request timed out.";
    default:
      return "Data source busy.";
  }
}

export const RetryButton = memo(function RetryButton({
  onRetry,
  initialDelay = 60,
  message,
  errorCode = null,
  autoRetry = true,
  size = "sm",
}) {
  const [countdown, setCountdown] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);
  const intervalRef = useRef(null);

  // Clear interval on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Start countdown when component mounts with a delay
  useEffect(() => {
    if (!autoRetry || initialDelay <= 0) return;

    setCountdown(initialDelay);
    intervalRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(intervalRef.current);
          // Trigger auto-retry
          handleAutoRetry();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAutoRetry = useCallback(async () => {
    setIsRetrying(true);
    try {
      await onRetry();
    } catch (e) {
      console.warn("[RetryButton] Auto-retry failed:", e);
    } finally {
      setIsRetrying(false);
    }
  }, [onRetry]);

  const handleManualRetry = useCallback(async () => {
    // Cancel countdown
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setCountdown(0);
    setIsRetrying(true);
    try {
      await onRetry();
    } catch (e) {
      // Restart countdown on failure
      setCountdown(initialDelay);
      intervalRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            clearInterval(intervalRef.current);
            handleAutoRetry();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } finally {
      setIsRetrying(false);
    }
  }, [onRetry, initialDelay, handleAutoRetry]);

  const userMessage = _getMessage(errorCode, message);
  const displaySize = SIZE_MAP[size] || SIZE_MAP.sm;

  return (
    <div
      className="flex flex-col items-center gap-2 py-3 px-4 rounded"
      style={{
        background: "rgba(18, 20, 24, 0.5)",
        border: "1px solid var(--border)",
      }}
      data-testid="retry-button-container"
      role="status"
      aria-live="polite"
    >
      {/* Error message */}
      <div className={`${displaySize} text-slate-400 text-center`}>
        {userMessage}
      </div>

      {/* Countdown + manual retry */}
      <div className="flex items-center gap-2">
        {countdown > 0 && (
          <span
            className="text-[11px] mono text-amber-400"
            data-testid="retry-countdown"
          >
            Retrying in {countdown}s…
          </span>
        )}

        <button
          onClick={handleManualRetry}
          disabled={isRetrying}
          className={`${displaySize} rounded cursor-pointer transition-opacity`}
          style={{
            background: "var(--bg-2)",
            border: "1px solid var(--border)",
            color: isRetrying ? "#64748b" : "#5eead4",
            opacity: isRetrying ? 0.6 : 1,
            cursor: isRetrying ? "wait" : "pointer",
          }}
          data-testid="retry-button"
        >
          {isRetrying ? "Retrying…" : "Retry Now"}
        </button>
      </div>

      {/* Error code badge */}
      {errorCode && (
        <span
          className="text-[9px] mono text-slate-600"
          style={{
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.2)",
            padding: "1px 4px",
            borderRadius: 3,
            color: "#f87171",
          }}
        >
          HTTP {errorCode}
        </span>
      )}
    </div>
  );
});

// Convenience wrapper: ErrorState shows a full error card with retry
export const ErrorState = memo(function ErrorState({
  error,
  onRetry,
  title = "Failed to load data",
}) {
  // Parse error code from various error shapes
  let errorCode = null;
  if (error) {
    if (typeof error === "object") {
      errorCode = error.status_code || error.response?.status || null;
    }
    if (typeof error === "string") {
      const match = error.match(/HTTP (\d+)/);
      if (match) errorCode = match[1];
    }
  }

  const codeStr = errorCode !== null && errorCode !== undefined ? String(errorCode) : null;
  const isRateLimited = codeStr === "429";
  // 404 ("No options data for <ticker>") is permanent for that ticker — never
  // auto-retry it; the manual button stays for a deliberate re-attempt.
  const isNotFound = codeStr === "404";
  const initialDelay = isRateLimited ? 60 : 10;

  return (
    <div
      className="panel p-4 text-center"
      data-testid="error-state"
      role="alert"
    >
      <div className="text-2xl mb-2">📡</div>
      <div className="text-sm font-semibold text-slate-200 mb-1">
        {title}
      </div>
      <div className="text-[11px] text-slate-500 mb-3">
        {typeof error === "string" ? error : error?.message || "An unexpected error occurred"}
      </div>
      <RetryButton
        onRetry={onRetry}
        errorCode={codeStr}
        message={isNotFound ? "No options data for this ticker — try another symbol." : undefined}
        initialDelay={initialDelay}
        autoRetry={!isNotFound}
      />
    </div>
  );
});

export default RetryButton;
