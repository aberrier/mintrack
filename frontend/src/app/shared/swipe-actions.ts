import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';

/** How far a finger moves before the gesture counts as a swipe or a scroll. */
const SLOP_PX = 10;

/**
 * A row that slides left under a finger or a mouse to uncover its actions, projected with `swipeAction`. Only
 * `transform` changes, so dragging never triggers a layout. The uncovered actions are hidden from keyboards and
 * screen readers while closed: the row must offer the same actions another way, such as a menu.
 */
@Component({
  selector: 'app-swipe-actions',
  template: `
    <div
      #actions
      class="actions"
      [attr.aria-hidden]="$open() ? null : 'true'"
      [attr.inert]="$open() ? null : ''"
      (click)="close()">
      <ng-content select="[swipeAction]" />
    </div>
    <div #front class="front" (transitionend)="hideActionsWhenClosed()">
      <ng-content />
    </div>
  `,
  styles: `
    :host {
      position: relative;
      display: block;
      overflow: hidden;
      touch-action: pan-y;
    }
    .actions {
      position: absolute;
      visibility: hidden;
      inset-block: 0;
      right: 0;
      display: flex;
    }
    .front {
      position: relative;
      background: var(--mat-sys-surface);
    }
    .front.settling {
      transition: transform 200ms cubic-bezier(0.2, 0, 0, 1);
    }
  `,
  host: { '(keydown.escape)': 'close()' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SwipeActions {
  private readonly actions = viewChild.required<ElementRef<HTMLElement>>('actions');
  private readonly front = viewChild.required<ElementRef<HTMLElement>>('front');

  protected readonly $open = signal(false);

  constructor() {
    const host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    let start: { x: number; y: number; offset: number; pointer: number } | null = null;
    let dragging = false;
    let offset = 0;
    let swallowClick = false;

    const down = (event: PointerEvent) => {
      if (!event.isPrimary || event.button !== 0) return;
      start = {
        x: event.clientX,
        y: event.clientY,
        offset: this.$open() ? -this.width() : 0,
        pointer: event.pointerId,
      };
      dragging = false;
      // A touch drag ends without a click: the flag must not swallow the next tap.
      swallowClick = false;
    };
    const move = (event: PointerEvent) => {
      if (!start || event.pointerId !== start.pointer) return;
      const dx = event.clientX - start.x;
      const dy = event.clientY - start.y;
      if (!dragging) {
        if (Math.abs(dy) > SLOP_PX && Math.abs(dy) >= Math.abs(dx)) start = null;
        else if (Math.abs(dx) > SLOP_PX) {
          dragging = true;
          host.setPointerCapture(event.pointerId);
          this.front().nativeElement.classList.remove('settling');
        }
        return;
      }
      offset = Math.min(0, Math.max(-this.width(), start.offset + dx));
      this.translate(offset);
    };
    const up = () => {
      if (dragging) {
        swallowClick = true;
        this.settle(offset < -this.width() / 2);
      }
      start = null;
      dragging = false;
    };
    // The click that ends a drag must not follow the link under the finger.
    const click = (event: MouseEvent) => {
      if (!swallowClick) return;
      swallowClick = false;
      event.preventDefault();
      event.stopPropagation();
    };

    host.addEventListener('pointerdown', down);
    host.addEventListener('pointermove', move);
    host.addEventListener('pointerup', up);
    host.addEventListener('pointercancel', up);
    host.addEventListener('click', click, true);
    inject(DestroyRef).onDestroy(() => {
      host.removeEventListener('pointerdown', down);
      host.removeEventListener('pointermove', move);
      host.removeEventListener('pointerup', up);
      host.removeEventListener('pointercancel', up);
      host.removeEventListener('click', click, true);
    });
  }

  close(): void {
    if (this.$open()) this.settle(false);
  }

  private settle(open: boolean): void {
    const front = this.front().nativeElement;
    const moved = front.style.transform !== '';
    this.$open.set(open);
    front.classList.add('settling');
    this.translate(open ? -this.width() : 0);
    // Nothing to animate back: no transitionend will come.
    if (!moved) this.hideActionsWhenClosed();
  }

  /** Behind a closed row, the actions stay hidden so not even an antialiased edge shows. */
  protected hideActionsWhenClosed(): void {
    if (!this.$open()) this.actions().nativeElement.style.visibility = '';
  }

  private translate(offset: number): void {
    this.front().nativeElement.style.transform = offset ? `translateX(${offset}px)` : '';
    if (offset) this.actions().nativeElement.style.visibility = 'visible';
  }

  private width(): number {
    return this.actions().nativeElement.offsetWidth;
  }
}
