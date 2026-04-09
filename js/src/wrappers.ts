import { TracerProvider, MutableSpan } from './tracer';
import type { MemoryOperation } from './types';

interface WrapperOptions {
  captureContent?: boolean;
  [key: string]: unknown;
}

type AnyAsyncFn<TArgs extends unknown[], TReturn> = (...args: TArgs) => Promise<TReturn>;

function createWrapper<TArgs extends unknown[], TReturn>(
  operation: MemoryOperation,
  fn: AnyAsyncFn<TArgs, TReturn>,
  options: WrapperOptions = {},
): AnyAsyncFn<TArgs, TReturn> {
  const { captureContent = true, ...extraAttrs } = options;
  const attributes: Record<string, unknown> = { ...extraAttrs };

  return async (...args: TArgs): Promise<TReturn> => {
    const provider = TracerProvider.get();

    if (!provider.sampler.shouldSample()) {
      return fn(...args);
    }

    const tracer = provider.getTracer('memorylens.wrappers');
    const span = tracer.startSpan(operation, attributes);

    if (captureContent && args.length > 0) {
      const firstArg = args[0];
      if (typeof firstArg === 'string') {
        span.setContent(firstArg, undefined);
      }
    }

    try {
      const result = await fn(...args);
      span.setStatus('ok');

      if (captureContent && result !== undefined) {
        if (typeof result === 'string') {
          span.setContent(undefined, result);
        } else if (result !== null && typeof result === 'object') {
          span.setContent(undefined, JSON.stringify(result));
        }
      }

      tracer.endSpan(span);
      return result;
    } catch (error) {
      span.setError(error);
      tracer.endSpan(span);
      throw error;
    }
  };
}

export function instrumentWrite<TArgs extends unknown[], TReturn>(
  fn: AnyAsyncFn<TArgs, TReturn>,
  options?: WrapperOptions,
): AnyAsyncFn<TArgs, TReturn> {
  return createWrapper('memory.write', fn, options);
}

export function instrumentRead<TArgs extends unknown[], TReturn>(
  fn: AnyAsyncFn<TArgs, TReturn>,
  options?: WrapperOptions,
): AnyAsyncFn<TArgs, TReturn> {
  return createWrapper('memory.read', fn, options);
}

export function instrumentCompress<TArgs extends unknown[], TReturn>(
  fn: AnyAsyncFn<TArgs, TReturn>,
  options?: WrapperOptions,
): AnyAsyncFn<TArgs, TReturn> {
  return createWrapper('memory.compress', fn, options);
}

export function instrumentUpdate<TArgs extends unknown[], TReturn>(
  fn: AnyAsyncFn<TArgs, TReturn>,
  options?: WrapperOptions,
): AnyAsyncFn<TArgs, TReturn> {
  return createWrapper('memory.update', fn, options);
}

export function endSpanManually(span: MutableSpan): void {
  const provider = TracerProvider.get();
  const tracer = provider.getTracer('memorylens.wrappers');
  tracer.endSpan(span);
}
