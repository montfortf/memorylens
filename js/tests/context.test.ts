import { describe, it, expect } from 'vitest';
import { runWithContext, getCurrentContext } from '../src/context';

describe('context', () => {
  it('returns undefined outside context', () => {
    expect(getCurrentContext()).toBeUndefined();
  });

  it('returns context inside runWithContext', () => {
    runWithContext({ agentId: 'bot', sessionId: 's1' }, () => {
      const ctx = getCurrentContext();
      expect(ctx).toBeDefined();
      expect(ctx!.agentId).toBe('bot');
      expect(ctx!.sessionId).toBe('s1');
    });
  });

  it('restores undefined after context exits', () => {
    runWithContext({ agentId: 'bot' }, () => {});
    expect(getCurrentContext()).toBeUndefined();
  });

  it('nests contexts correctly', () => {
    runWithContext({ agentId: 'outer' }, () => {
      expect(getCurrentContext()!.agentId).toBe('outer');
      runWithContext({ agentId: 'inner' }, () => {
        expect(getCurrentContext()!.agentId).toBe('inner');
      });
      expect(getCurrentContext()!.agentId).toBe('outer');
    });
  });

  it('works with async functions', async () => {
    await runWithContext({ agentId: 'async-bot' }, async () => {
      await new Promise(resolve => setTimeout(resolve, 10));
      expect(getCurrentContext()!.agentId).toBe('async-bot');
    });
  });

  it('context carries userId', () => {
    runWithContext({ userId: 'u42', agentId: 'agent', sessionId: 'sess' }, () => {
      const ctx = getCurrentContext();
      expect(ctx!.userId).toBe('u42');
    });
  });
});
