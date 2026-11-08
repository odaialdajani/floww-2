// One finite arrangement domain for rendering, reducer counts and persistence.
// Legacy IDs stay valid; Single remains the default and unknown-ID fallback.
export const LAYOUT_PRESETS = [
  { id: 'single', label: 'Single pane', panes: 1, className: 'pane-layout-single', quick: true },
  { id: 'split', label: 'Split · 2 panes', panes: 2, className: 'pane-layout-split', quick: true },
  { id: 'three', label: 'Three panes', panes: 3, className: 'pane-layout-three', quick: true },
  { id: 'two-stack', label: '2-Stack', panes: 2, className: 'pane-layout-two-stack' },
  { id: 'three-stack', label: '3-Stack', panes: 3, className: 'pane-layout-three-stack' },
  { id: 'one-plus-two', label: '1 + 2', panes: 3, className: 'pane-layout-one-plus-two' },
  { id: 'one-beside-two', label: '1 | 2', panes: 3, className: 'pane-layout-one-beside-two' },
  { id: 'four-grid', label: '4-Grid', panes: 4, className: 'pane-layout-four-grid' },
  { id: 'four-up', label: '4-Up', panes: 4, className: 'pane-layout-four-up' },
  { id: 'four-stack', label: '4-Stack', panes: 4, className: 'pane-layout-four-stack' },
  { id: 'five-stack', label: '5-Stack', panes: 5, className: 'pane-layout-five-stack' },
];
export function layoutById(id) {
  return LAYOUT_PRESETS.find(preset => preset.id === id) || LAYOUT_PRESETS[0];
}
