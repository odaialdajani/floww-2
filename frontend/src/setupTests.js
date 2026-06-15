// Jest setup — runs before each test file. Adds @testing-library/jest-dom
// matchers (toBeInTheDocument, toHaveTextContent, etc.) onto Jest expect.
import '@testing-library/jest-dom';

// jsdom does not implement IntersectionObserver. Components that lazy-render
// below-the-fold content (e.g. HeatseekerDashboard's LazyRow) construct one in a
// mount effect, which throws "IntersectionObserver is not defined" under the test
// environment. Provide a minimal polyfill that immediately reports the observed
// element as intersecting, so lazy content renders synchronously in tests.
if (typeof global.IntersectionObserver === 'undefined') {
  class IntersectionObserver {
    constructor(callback) {
      this._callback = callback;
    }
    observe(target) {
      // Report as intersecting on the next microtask so React effects settle.
      this._callback(
        [{ isIntersecting: true, target, intersectionRatio: 1 }],
        this
      );
    }
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  global.IntersectionObserver = IntersectionObserver;
  window.IntersectionObserver = IntersectionObserver;
}
