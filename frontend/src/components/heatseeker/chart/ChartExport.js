// B27 export: engine capture controls primitives/crosshair; DOM sidecar separate.
// Clipboard denied states explicit. The composed SVG starts from the CURRENT
// pane composition and preserves the layer flags + watermarks — ChartWorkspace
// mounts this against the live state (never a fabricated chart).
export function exportPlan({ includePrimitives = true, includeCrosshair = false, sidecar = false } = {}) {
  return { engine: { includePrimitives, includeCrosshair }, sidecar, clipboard: 'prompt' };
}

// Clipboard states are explicit and visible: 'copied' | 'denied'.
export function clipboardState(error) {
  return error ? 'denied' : 'copied';
}

// Composite export: one SVG describing the whole composition — every pane
// with its instrument and fit mode, the data-quality stamp, and the
// source/proxy/replay watermark. Layers honor the export plan flags.
export function composeExportSvg({ layoutId = 'single', panes = [], fitMode = 'fit-visible', watermarkText = '', quality = null, plan = exportPlan() } = {}) {
  const width = 1200;
  const paneW = 1160;
  const paneH = 220;
  const height = 80 + panes.length * (paneH + 16) + 60;
  const escapeXml = (text) => String(text ?? '').replace(/&/g, '\u0026amp;').replace(/</g, '\u0026lt;').replace(/>/g, '\u0026gt;').replace(/"/g, '\u0026quot;');
  const paneRects = panes.map((pane, index) => {
    const y = 70 + index * (paneH + 16);
    const focused = pane.focused ? ' (focused)' : '';
    return `<g><rect x="20" y="${y}" width="${paneW}" height="${paneH}" fill="#101820" stroke="${pane.focused ? '#e3c16a' : '#232c36'}" stroke-width="2"/><text x="34" y="${y + 28}" fill="#dce8f2" font-size="18" font-family="monospace">${escapeXml(pane.symbol)}${escapeXml(focused)} · fit ${escapeXml(fitMode)}</text><text x="34" y="${y + 54}" fill="#8ba3b0" font-size="13" font-family="monospace">${plan.engine.includePrimitives ? 'primitives:on' : 'primitives:off'} · crosshair:${plan.engine.includeCrosshair ? 'on' : 'off'}</text></g>`;
  }).join('');
  const qualityStamp = quality
    ? `<text x="20" y="${height - 44}" fill="#8ba3b0" font-size="13" font-family="monospace">quality ${escapeXml(quality.status ?? 'unknown')} · latest ${escapeXml(quality.sourceTime ?? 'time unknown')} · ${escapeXml(quality.coverage ?? '')}</text>`
    : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="${width}" height="${height}" fill="#0b1219"/><text x="20" y="40" fill="#f2d795" font-size="22" font-family="monospace">FLOWW chart export · ${escapeXml(layoutId)} composition</text>${paneRects}${qualityStamp}<text x="20" y="${height - 18}" fill="#6f8896" font-size="13" font-family="monospace">${escapeXml(watermarkText)}</text></svg>`;
}
