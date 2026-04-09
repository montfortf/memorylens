export class Sampler {
  private rate: number;

  constructor(rate: number = 1.0) {
    if (rate < 0 || rate > 1) {
      throw new Error(`Sample rate must be between 0.0 and 1.0, got ${rate}`);
    }
    this.rate = rate;
  }

  shouldSample(): boolean {
    if (this.rate === 1.0) return true;
    if (this.rate === 0.0) return false;
    return Math.random() < this.rate;
  }

  getRate(): number {
    return this.rate;
  }
}
