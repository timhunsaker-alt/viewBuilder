import "@testing-library/jest-dom/vitest";

// jsdom does not implement ResizeObserver, which @xyflow/react relies on to measure node
// dimensions before it will render edges between them. Report a plausible fixed size on
// observe() so node measurement completes and edges render in tests.
class ResizeObserverStub {
  #callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.#callback = callback;
  }

  observe(target: Element) {
    this.#callback(
      [{ target, contentRect: { width: 150, height: 40 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve() {}
  disconnect() {}
}
// biome-ignore lint/suspicious/noExplicitAny: test-environment global polyfill
(globalThis as any).ResizeObserver = ResizeObserverStub;
