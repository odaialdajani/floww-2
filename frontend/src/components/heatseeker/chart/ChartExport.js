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

// Capture the actual rendered SVG layers, including candles, saved nodes,
// drawings, volume and CVD. Resolved styles make the image standalone.
export function captureChartSvgs(root, plan=exportPlan()) {
  if(!root)return [];
  const slots=[...root.querySelectorAll('.pane-slot')];
  return (slots.length?slots:[root]).map(slot=>{
    const nodes=[...slot.querySelectorAll('.recorded-price-chart svg')];
    return nodes.map(svg=>{
      const copy=svg.cloneNode(true),originals=[svg,...svg.querySelectorAll('*')],copies=[copy,...copy.querySelectorAll('*')];
      const props=['fill','stroke','stroke-width','color','opacity','font-family','font-size','font-weight','text-anchor'];
      originals.forEach((el,i)=>{const styles=window.getComputedStyle(el);props.forEach(key=>{const value=styles.getPropertyValue(key);if(value)copies[i].style.setProperty(key,value);});});
      const box=(svg.getAttribute('viewBox')||'').split(/\s+/).map(Number);
      const width=box[2]||svg.getBoundingClientRect().width,height=box[3]||svg.getBoundingClientRect().height;
      if(!(width>0&&height>0))return null;
      copy.removeAttribute('xmlns');copy.removeAttribute('class');
      if(!plan.engine.includeCrosshair)copy.querySelectorAll('[data-export-layer="crosshair"]').forEach(el=>el.remove());
      if(!plan.engine.includePrimitives)copy.querySelectorAll('[data-testid="drawing-layer"]').forEach(el=>el.remove());
      copy.setAttribute('width',String(width));copy.setAttribute('height',String(height));
      copy.style.width=width+'px';copy.style.height=height+'px';
      return {svg:new XMLSerializer().serializeToString(copy),width,height};
    }).filter(Boolean);
  });
}

// Layout identity alone cannot substitute for an image of the chart.
export function composeExportSvg({layoutId='single',panes=[],fitMode='fit-visible',watermarkText='',quality=null,charts=[],plan=exportPlan()}={}) {
  if(!charts.length||!charts.some(layers=>layers.length))throw new Error('No rendered charts available for export');
  if(charts.length!==panes.length || charts.some(layers=>!layers.length))throw new Error('Chart pane unavailable — export requires every pane');
  const escapeXml=text=>String(text??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const width=Math.max(800,...charts.flat().map(layer=>layer.width))+40;
  let offset=64;
  const content=charts.map((layers,index)=>{
    const pane=panes[index]||{},heading=`${pane.symbol||'Chart'}${pane.focused?' (focused)':''} · fit ${fitMode}`;
    let result=`<text x="20" y="${offset}" fill="#dce8f2" font-size="14">${escapeXml(heading)}</text>`;offset+=14;
    for(const layer of layers){result+=`<g transform="translate(20 ${offset})">${layer.svg}</g>`;offset+=layer.height+6;}
    offset+=24;return result;
  }).join('');
  const stamp=(quality?`quality ${quality.status??'unknown'} · latest ${quality.sourceTime??'time unknown'} · ${quality.coverage??''} · `:'')+`primitives:${plan.engine.includePrimitives?'on':'off'} · crosshair:${plan.engine.includeCrosshair?'on':'off'}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${offset+60}" viewBox="0 0 ${width} ${offset+60}"><rect width="100%" height="100%" fill="#111111"/><text x="20" y="30" fill="#f2d795" font-size="18">FLOWW chart export · ${escapeXml(layoutId)} composition</text>${content}<text x="20" y="${offset+12}" fill="#aab6c0" font-size="12">${escapeXml(stamp)}</text><text x="20" y="${offset+36}" fill="#aab6c0" font-size="12">${escapeXml(watermarkText)}</text></svg>`;
}
