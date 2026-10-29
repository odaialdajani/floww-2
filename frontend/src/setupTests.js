// Jest setup — runs before each test file. Adds @testing-library/jest-dom
// matchers (toBeInTheDocument, toHaveTextContent, etc.) onto Jest expect.
import '@testing-library/jest-dom';

// JSDOM stubs for browser APIs Plotly / <audio> expect. JSDOM doesn't ship
// URL.createObjectURL/revokeObjectURL and HTMLMediaElement.prototype.play
// only emits a console.error. Stubbing all five keeps visual.test.jsx
// mountable and silences harmless noise across the FlowseekerProTab suites.
if (typeof window.URL.createObjectURL !== "function") {
  window.URL.createObjectURL = () => "blob:jest-stub";
}
if (typeof window.URL.revokeObjectURL !== "function") {
  window.URL.revokeObjectURL = () => {};
}
window.HTMLMediaElement.prototype.play = () => Promise.resolve();
window.HTMLMediaElement.prototype.pause = () => {};
window.HTMLMediaElement.prototype.load = () => {};

// jsdom lacks PointerEvent, so testing-library's fireEvent.pointer* fell back to
// a bare Event (clientX/clientY undefined) and production pointer-drawing
// handlers honestly refused non-finite coordinates. Define a jsdom-compatible
// PointerEvent so pointer geometry is testable with real coordinates.
if (typeof window !== 'undefined' && !window.PointerEvent) {
  window.PointerEvent = class PointerEvent extends MouseEvent {
    constructor(type, opts = {}) {
      super(type, opts);
      this.pointerType = opts.pointerType || '';
      this.pointerId = opts.pointerId ?? 1;
      this.width = opts.width ?? 0;
      this.height = opts.height ?? 0;
      this.pressure = opts.pressure ?? 0;
      this.isPrimary = opts.isPrimary ?? true;
    }
  };
}
