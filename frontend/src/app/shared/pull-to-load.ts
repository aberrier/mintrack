import { CdkScrollable } from '@angular/cdk/scrolling';
import { DestroyRef, Directive, inject, input, output } from '@angular/core';

/** How close to the top, in pixels, scrolling counts as reaching for more. */
const NEAR_TOP_PX = 300;
/** How far a finger pulls down at the top before it counts. */
const PULL_PX = 40;

/**
 * Asks for more above the content of the shell's scrolling area: a wheel turned up or a finger pulling down at its
 * very top, or, once `nearTop` is on, any scroll that comes within reach of the top.
 */
@Directive({ selector: '[appPullToLoad]' })
export class PullToLoad {
  /** Scrolling near the top asks for more too, once there is something above to read. */
  readonly nearTop = input(false);
  readonly appPullToLoad = output<void>();

  constructor() {
    const scroller = inject(CdkScrollable, { optional: true })?.getElementRef().nativeElement;
    if (!scroller) return;
    const listeners = new AbortController();
    const options = { passive: true, signal: listeners.signal };
    let pullFrom: number | null = null;
    const ask = () => this.appPullToLoad.emit();

    scroller.addEventListener('scroll', () => this.nearTop() && scroller.scrollTop < NEAR_TOP_PX && ask(), options);
    scroller.addEventListener('wheel', (event) => event.deltaY < 0 && scroller.scrollTop <= 0 && ask(), options);
    scroller.addEventListener(
      'touchstart',
      (event) => (pullFrom = scroller.scrollTop <= 0 ? event.touches[0].clientY : null),
      options,
    );
    scroller.addEventListener(
      'touchmove',
      (event) => {
        if (pullFrom === null || event.touches[0].clientY - pullFrom < PULL_PX) return;
        pullFrom = null;
        ask();
      },
      options,
    );
    inject(DestroyRef).onDestroy(() => listeners.abort());
  }
}
