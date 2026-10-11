// P3 tool registry: ONLY evidence-backed tools are listed (Atlas guide +
// preset docs name these nine). Anything else is unsupported — never an
// invented 17. Remaining Atlas tools stay unverified until the guide names
// them; see UNVERIFIED_TOOLS below (not constructible).
export const DRAWING_TOOLS = [
  { id: 'trend', anchors: 2, magnet: true, family: 'line' },
  { id: 'horizontal', anchors: 1, magnet: true, family: 'line' },
  { id: 'horizontal-ray', anchors: 1, magnet: true, family: 'line' },
  { id: 'vertical', anchors: 1, magnet: false, family: 'line' },
  { id: 'rectangle', anchors: 2, magnet: false, family: 'shape' },
  { id: 'arrow', anchors: 2, magnet: false, family: 'shape' },
  { id: 'brush', anchors: 2, magnet: false, family: 'free' },
  { id: 'fib', anchors: 2, magnet: true, family: 'fib' },
  { id: 'text', anchors: 1, magnet: false, family: 'label' },
];
// Named in census counts but NOT in retrieved evidence — do not construct.
export const UNVERIFIED_TOOLS = [];
export function isSupportedTool(id) {
  return DRAWING_TOOLS.some((t) => t.id === id);
}
export function anchorsFor(id) {
  const tool = DRAWING_TOOLS.find((t) => t.id === id);
  return tool ? tool.anchors : 0;
}
export function toolFamily(id) {
  const tool = DRAWING_TOOLS.find((t) => t.id === id);
  return tool ? tool.family : null;
}
