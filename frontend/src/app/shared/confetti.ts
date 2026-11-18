import { DOCUMENT, inject, Injectable } from '@angular/core';

/**
 * Confetti over the screen, nothing when the user prefers reduced motion. The library loads on the first throw, and
 * draws without a worker, which the content security policy would refuse as a blob.
 */
@Injectable({ providedIn: 'root' })
export class Confetti {
  private readonly document = inject(DOCUMENT);

  launch(): void {
    if (this.document.defaultView?.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    void this.throw();
  }

  private async throw(): Promise<void> {
    const { default: confetti } = await import('canvas-confetti');
    const canvas = this.document.createElement('canvas');
    canvas.dataset['testid'] = 'confetti';
    canvas.setAttribute('aria-hidden', 'true');
    Object.assign(canvas.style, {
      position: 'fixed',
      inset: '0',
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      zIndex: '1000',
    });
    this.document.body.append(canvas);
    const fire = confetti.create(canvas, { resize: true, useWorker: false });
    try {
      await fire({ particleCount: 160, spread: 100, startVelocity: 45, origin: { y: 0.7 } });
    } finally {
      fire.reset();
      canvas.remove();
    }
  }
}
