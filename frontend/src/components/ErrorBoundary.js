/**
 * ErrorBoundary.jsx
 *
 * React error boundary that catches render errors in child components
 * and displays a user-friendly fallback UI instead of crashing.
 *
 * Catches:
 *   - Render-time errors (TypeError, ReferenceError, etc.)
 *   - Children mounting errors
 *
 * Does NOT catch:
 *   - Event handlers (use try/catch in handlers)
 *   - Async errors (use error state in hooks)
 *   - Server-side rendering errors
 *
 * Features:
 *   - User-friendly message (no stack trace shown)
 *   - "Retry" button to attempt re-render
 *   - Error count display for repeated failures
 *   - Logs error details to console for debugging
 */

import React, { Component } from "react";
import {reportProblem} from "../diagnostics/problemTracking";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0,
    };
    this.retryKey = 0;
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    reportProblem({kind:"browser_error",name:error?.name});
    // Log for debugging — not shown to user
    console.error("[ErrorBoundary] Caught render error:", error);
    console.error("[ErrorBoundary] Component stack:", errorInfo?.componentStack);

    // Track error count for repeated failures
    this.setState(prev => ({
      errorInfo,
      errorCount: prev.errorCount + 1,
    }));

    // Optional: report to error tracking service
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  handleRetry = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
    this.retryKey += 1;
  };

  render() {
    if (this.state.hasError) {
      const { errorCount } = this.state;
      const { fallback, children } = this.props;
      const isRepeated = errorCount > 1;

      // If custom fallback renderer provided, use it
      if (fallback) {
        return fallback({
          error: this.state.error,
          errorCount,
          retry: this.handleRetry,
        });
      }

      // Default fallback UI
      return (
        <div
          className="flex flex-col items-center justify-center p-6 text-center"
          style={{
            minHeight: 200,
            background: "var(--panel)",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
          role="alert"
          data-testid="error-boundary-fallback"
        >
          <div className="text-3xl mb-3">⚠️</div>

          <div className="text-sm font-semibold text-slate-200 mb-1">
            Something went wrong
          </div>
          <div className="text-[10px] text-red-400 mb-2 max-w-xs font-mono break-all" style={{ maxHeight: 80, overflow: "auto" }}>
            {String(this.state.error?.message || this.state.error || "").slice(0, 300)}
          </div>

          <div className="text-[11px] text-slate-500 mb-4 max-w-xs">
            {isRepeated
              ? `This section failed to load ${errorCount} times. The data source may be unavailable.`
              : "This section couldn't render. This is usually a temporary issue."}
          </div>

          <button
            onClick={this.handleRetry}
            className="btn text-[11px]"
            data-testid="error-boundary-retry"
            style={{
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              color: "#5eead4",
              padding: "6px 16px",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            Try Again
          </button>

          {isRepeated && (
            <div className="text-[10px] text-slate-600 mt-3">
              If this persists, try refreshing the page.
            </div>
          )}
        </div>
      );
    }

    // Use key to force remount on retry
    return (
      <React.Fragment key={this.retryKey}>
        {this.props.children}
      </React.Fragment>
    );
  }
}
