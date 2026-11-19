import { afterNextRender, DestroyRef, Directive, ElementRef, inject, Injector } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';

/**
 * Saves the host element's scroll position per history entry and restores it on back and forward; a new page starts at
 * the top, or at the element its URL's fragment names. The router's own scroll restoration and anchor scrolling only
 * handle the window, which never scrolls in the shell.
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

    const router = inject(Router);
    router.events.pipe(takeUntilDestroyed(inject(DestroyRef))).subscribe((event) => {
      if (event instanceof NavigationStart) {
        positions.set(entry, element.scrollTop);
        target = event.restoredState?.navigationId ?? event.id;
      } else if (event instanceof NavigationEnd) {
        entry = target;
        const saved = positions.get(entry);
        // A new page opened at a fragment starts at the element of that id, if there is one.
        const fragment = saved === undefined ? router.parseUrl(event.urlAfterRedirects).fragment : null;
        afterNextRender(
          {
            write: () => {
              const anchor = fragment ? element.ownerDocument.getElementById(fragment) : null;
              if (anchor) anchor.scrollIntoView();
              else element.scrollTop = saved ?? 0;
            },
          },
          { injector },
        );
      }
    });
  }
}
