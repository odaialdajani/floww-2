// B27 export: engine capture controls primitives/crosshair; DOM sidecar separate.
// Clipboard denied states explicit.
export function exportPlan({ includePrimitives = true, includeCrosshair = false, sidecar = false } = {}) {
  return { engine: { includePrimitives, includeCrosshair }, sidecar, clipboard: 'prompt' };
}
