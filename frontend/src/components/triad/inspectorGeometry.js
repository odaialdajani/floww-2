const LINE_HEIGHT_FACTOR = 1.2;
const SAFE_AREA = "env(safe-area-inset-bottom)";

export const FLOATING_CONTROL_MARGIN_PX = 16;
export const INSPECTOR_TOP_OFFSET_PX = 6;

export const APP_HEALTH_CHIP = {
  fontSizePx: 12,
  paddingPx: 8,
  borderPx: 2,
  minHeightPx: 28,
  wideBottomPx: 84,
  narrowBottomPx: 116,
};

export const ASK_FLOW_OPENER = {
  fontSizePx: 16,
  paddingPx: 20,
  borderPx: 2,
  wideBottomPx: 18,
  narrowBottomPx: 64,
};

export const controlHeight = ({ fontSizePx, paddingPx, borderPx, minHeightPx }) =>
  Math.max(minHeightPx || 0, Math.ceil(fontSizePx * LINE_HEIGHT_FACTOR) + paddingPx + borderPx);

export const APP_HEALTH_CHIP_HEIGHT_PX = controlHeight(APP_HEALTH_CHIP);
export const ASK_FLOW_OPENER_HEIGHT_PX = controlHeight(ASK_FLOW_OPENER);

export const controlBandTop = (healthBottomPx, askBottomPx) =>
  Math.max(healthBottomPx + APP_HEALTH_CHIP_HEIGHT_PX, askBottomPx + ASK_FLOW_OPENER_HEIGHT_PX);

export const INSPECTOR_CLEARANCE = {
  wide: controlBandTop(APP_HEALTH_CHIP.wideBottomPx, ASK_FLOW_OPENER.wideBottomPx) + FLOATING_CONTROL_MARGIN_PX,
  narrow: controlBandTop(APP_HEALTH_CHIP.narrowBottomPx, ASK_FLOW_OPENER.narrowBottomPx) + FLOATING_CONTROL_MARGIN_PX,
};

export const inspectorDockStyle = () => ({
  "--tdk-inspector-top-offset": `${INSPECTOR_TOP_OFFSET_PX}px`,
  "--tdk-floating-clearance-wide": `${INSPECTOR_CLEARANCE.wide}px`,
  "--tdk-floating-clearance-narrow": `${INSPECTOR_CLEARANCE.narrow}px`,
  "--tdk-dock-max-height": `calc(100vh - ${INSPECTOR_TOP_OFFSET_PX}px - ${INSPECTOR_CLEARANCE.wide}px - ${SAFE_AREA})`,
  "--tdk-dock-bottom-wide": `calc(${INSPECTOR_CLEARANCE.wide}px + ${SAFE_AREA})`,
  "--tdk-dock-bottom-compact": `calc(${INSPECTOR_CLEARANCE.narrow}px + ${SAFE_AREA})`,
});

export function inspectorAvailableHeight(viewportHeight, dockTop, controlsTop = []) {
  const bottom = controlsTop.length
    ? Math.min(viewportHeight, ...controlsTop) - FLOATING_CONTROL_MARGIN_PX
    : viewportHeight - INSPECTOR_CLEARANCE.wide;
  return Math.max(0, bottom - Math.max(INSPECTOR_TOP_OFFSET_PX, dockTop));
}

export function observeInspectorClearance(dock) {
  if (!dock) return undefined;
  const controls = [...document.querySelectorAll('aside[aria-label="App health"] > button, .lodestar-open')];
  let frame = 0;
  const measure = () => {
    frame = 0;
    const rect = dock.getBoundingClientRect();
    if (!rect.width) return;
    const tops = controls.map((control) => control.getBoundingClientRect())
      .filter((control) => control.width && control.height && control.left < rect.right && control.right > rect.left)
      .map((control) => control.top);
    const height = `${inspectorAvailableHeight(window.innerHeight, rect.top, tops)}px`;
    if (dock.style.getPropertyValue("--tdk-dock-max-height") !== height) {
      dock.style.setProperty("--tdk-dock-max-height", height);
    }
  };
  const schedule = () => {
    if (!frame) frame = window.requestAnimationFrame(measure);
  };
  const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
  [dock, dock.parentElement, dock.closest(".trinity-desktop"), ...controls]
    .filter(Boolean).forEach((element) => observer?.observe(element));
  window.addEventListener("resize", schedule);
  window.addEventListener("scroll", schedule, { capture: true, passive: true });
  measure();
  return () => {
    observer?.disconnect();
    window.cancelAnimationFrame(frame);
    window.removeEventListener("resize", schedule);
    window.removeEventListener("scroll", schedule, true);
  };
}
