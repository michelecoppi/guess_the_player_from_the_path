/**
 * A view module loaded with a dynamic `import()` the first time it is needed (#187): Shop,
 * Story and Events stay out of the startup bundle, so the Daily - the first screen - starts
 * sooner. The module is cached once loaded; a failed load (network drop while fetching the
 * chunk) is remembered so the page can offer a retry, and the next `load()` tries again.
 */
export interface LazyModule<T> {
  readonly module: T | null;
  readonly failed: boolean;
  load(): Promise<T>;
}

export function lazyModule<T>(loader: () => Promise<T>): LazyModule<T> {
  let module: T | null = null;
  let failed = false;
  let pending: Promise<T> | null = null;
  return {
    get module() {
      return module;
    },
    get failed() {
      return failed;
    },
    load() {
      if (module) return Promise.resolve(module);
      if (!pending) {
        failed = false;
        pending = loader().then(
          (loaded) => {
            module = loaded;
            pending = null;
            return loaded;
          },
          (err: unknown) => {
            failed = true;
            pending = null;
            throw err;
          },
        );
      }
      return pending;
    },
  };
}
