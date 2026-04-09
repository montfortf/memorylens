import { AsyncLocalStorage } from 'node:async_hooks';
import type { MemoryContext } from './types';

const contextStorage = new AsyncLocalStorage<MemoryContext>();

export function runWithContext<T>(ctx: MemoryContext, fn: () => T): T {
  return contextStorage.run(ctx, fn);
}

export function getCurrentContext(): MemoryContext | undefined {
  return contextStorage.getStore();
}
