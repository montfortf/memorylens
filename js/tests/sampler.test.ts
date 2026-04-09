import { describe, it, expect } from 'vitest';
import { Sampler } from '../src/sampler';

describe('Sampler', () => {
  it('rate 1.0 always returns true', () => {
    const s = new Sampler(1.0);
    for (let i = 0; i < 100; i++) {
      expect(s.shouldSample()).toBe(true);
    }
  });

  it('rate 0.0 always returns false', () => {
    const s = new Sampler(0.0);
    for (let i = 0; i < 100; i++) {
      expect(s.shouldSample()).toBe(false);
    }
  });

  it('default rate is 1.0', () => {
    const s = new Sampler();
    expect(s.getRate()).toBe(1.0);
    expect(s.shouldSample()).toBe(true);
  });

  it('getRate returns the configured rate', () => {
    const s = new Sampler(0.5);
    expect(s.getRate()).toBe(0.5);
  });

  it('throws on rate above 1', () => {
    expect(() => new Sampler(1.1)).toThrow('Sample rate must be between 0.0 and 1.0');
  });

  it('throws on negative rate', () => {
    expect(() => new Sampler(-0.1)).toThrow('Sample rate must be between 0.0 and 1.0');
  });

  it('rate 0.5 samples roughly half the time over many trials', () => {
    const s = new Sampler(0.5);
    let count = 0;
    const trials = 1000;
    for (let i = 0; i < trials; i++) {
      if (s.shouldSample()) count++;
    }
    // Expect between 35% and 65% (very loose bounds for flake avoidance)
    expect(count).toBeGreaterThan(trials * 0.35);
    expect(count).toBeLessThan(trials * 0.65);
  });
});
