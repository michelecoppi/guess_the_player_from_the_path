import { Window } from "happy-dom";

export interface TestDomContext {
  window: Window;
  document: Window["document"];
  container: HTMLElement;
  cleanup: () => void;
}

/**
 * Creates an isolated DOM environment using happy-dom.
 * Automatically cleans up DOM instances and restores global state when cleanup() is called.
 */
export function createTestDom(initialHtml = ""): TestDomContext {
  const window = new Window();
  const document = window.document;

  const container = document.createElement("div");
  container.id = "test-root";
  if (initialHtml) {
    container.innerHTML = initialHtml;
  }
  document.body.appendChild(container);

  return {
    window,
    document,
    container: container as unknown as HTMLElement,
    cleanup: () => {
      container.remove();
      window.close();
    },
  };
}

/**
 * Renders an HTML string into an isolated DOM element and returns it for inspection.
 */
export function renderToDom<T extends HTMLElement = HTMLElement>(html: string): { element: T; cleanup: () => void } {
  const dom = createTestDom(html);
  const element = (dom.container.firstElementChild || dom.container) as unknown as T;
  return {
    element,
    cleanup: dom.cleanup,
  };
}

/**
 * Attaches happy-dom to globalThis (window, document, HTMLElement, etc.) for testing code
 * that references global DOM objects directly.
 */
export function setupGlobalDom(initialHtml = ""): { cleanup: () => void; container: HTMLElement } {
  const window = new Window();
  const document = window.document;

  const originalWindow = (globalThis as any).window;
  const originalDocument = (globalThis as any).document;
  const originalHTMLElement = (globalThis as any).HTMLElement;
  const originalCustomEvent = (globalThis as any).CustomEvent;
  const originalEvent = (globalThis as any).Event;

  (globalThis as any).window = window;
  (globalThis as any).document = document;
  (globalThis as any).HTMLElement = (window as any).HTMLElement;
  (globalThis as any).CustomEvent = (window as any).CustomEvent;
  (globalThis as any).Event = (window as any).Event;

  const container = document.createElement("div");
  container.id = "app-root";
  if (initialHtml) {
    container.innerHTML = initialHtml;
  }
  document.body.appendChild(container);

  return {
    container: container as unknown as HTMLElement,
    cleanup: () => {
      container.remove();
      window.close();
      if (originalWindow !== undefined) (globalThis as any).window = originalWindow;
      else delete (globalThis as any).window;

      if (originalDocument !== undefined) (globalThis as any).document = originalDocument;
      else delete (globalThis as any).document;

      if (originalHTMLElement !== undefined) (globalThis as any).HTMLElement = originalHTMLElement;
      else delete (globalThis as any).HTMLElement;

      if (originalCustomEvent !== undefined) (globalThis as any).CustomEvent = originalCustomEvent;
      else delete (globalThis as any).CustomEvent;

      if (originalEvent !== undefined) (globalThis as any).Event = originalEvent;
      else delete (globalThis as any).Event;
    },
  };
}
