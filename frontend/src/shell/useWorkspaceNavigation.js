import { useCallback, useEffect, useState } from "react";
import { NAV_ITEMS } from "./navConfig";

const workspaceIds = new Set(NAV_ITEMS.map(item => item.id));
export function readWorkspace() {
  const id = new URLSearchParams(window.location.search).get("page");
  return workspaceIds.has(id) ? id : "heatseeker";
}

export default function useWorkspaceNavigation() {
  const [page, setPage] = useState(readWorkspace);
  useEffect(() => {
    const restore = () => setPage(readWorkspace());
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  const navigate = useCallback(id => {
    if (!workspaceIds.has(id)) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("page") !== id) {
      url.searchParams.set("page", id);
      window.history.pushState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    }
    setPage(id);
  }, []);
  return [page, navigate];
}
