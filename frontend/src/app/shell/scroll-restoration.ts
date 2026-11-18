import { afterNextRender, DestroyRef, Directive, ElementRef, inject, Injector } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';

/**
 * Saves the host element's scroll position per history entry and restores it on back and forward. The router's own
 * scroll restoration only handles the window, which never scrolls in the shell.
 */
@Directive({ selector: '[appScrollRestoration]' })
export class ScrollRestoration {
  constructor() {
    const element = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    const injector = inject(Injector);
    const positions = new Map<number, number>();
    // A history entry keeps the id of the navigation that created it, which back and forward hand back.
    let entry = 0;
    let target = 0;

    inject(Router)
      .events.pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe((event) => {
        if (event instanceof NavigationStart) {
          positions.set(entry, element.scrollTop);
          target = event.restoredState?.navigationId ?? event.id;
        } else if (event instanceof NavigationEnd) {
          entry = target;
          const top = positions.get(entry) ?? 0;
          afterNextRender({ write: () => (element.scrollTop = top) }, { injector });
        }
      });
  }
}
