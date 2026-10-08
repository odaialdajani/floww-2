import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/hooks/queryClient";
import "@/index.css";
import App from "@/App";
import { ThemeProvider } from "@/context/ThemeContext";
import { AuthProvider } from "@/context/AuthContext";
import {startProblemTracking, reportProblem} from "./diagnostics/problemTracking";
import "./NeutralTheme.css";
startProblemTracking();

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    console.error("REACT ERROR:", error, info);
    reportProblem({kind:"browser_error",name:error?.name});
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ color: "white", padding: 20, fontFamily: "monospace" }}>
          <h2>This screen could not load.</h2>
          <p>The problem has been recorded. Try opening the page again.</p>
          <button onClick={()=>window.location.reload()}>Reload page</button>
        </div>
      );
    }
    return this.props.children;
  }
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <ThemeProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ThemeProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  </React.StrictMode>
);
