export interface Instrumentor {
  instrument(options?: Record<string, unknown>): void;
  uninstrument(): void;
}
