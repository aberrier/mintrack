import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { injectTranslator } from '../core/i18n';

/**
 * Placeholders in the shape of what is loading, shown after a short delay: episode cards, a poster grid, a shelf of
 * posters, or the header of a show or movie page. Screen readers hear "Loading" once.
 */
@Component({
  selector: 'app-skeleton',
  template: `
    <span class="sr-only">{{ label() ?? translate('app.common.loading') }}</span>
    @switch (kind()) {
      @case ('cards') {
        <div class="card-list" aria-hidden="true">
          @for (i of $items(); track i) {
            <div class="flex items-center gap-4 rounded-2xl bg-surface-container-low p-2">
              <span class="skeleton aspect-[2/3] w-16 flex-none"></span>
              <span class="flex flex-1 flex-col gap-2">
                <span class="skeleton h-4 w-24"></span>
                <span class="skeleton h-5 w-20"></span>
                <span class="skeleton h-4 w-32"></span>
              </span>
            </div>
          }
        </div>
      }
      @case ('grid') {
        <div class="card-grid" aria-hidden="true">
          @for (i of $items(); track i) {
            <span class="skeleton aspect-[2/3]"></span>
          }
        </div>
      }
      @case ('shelf') {
        <div class="poster-row overflow-hidden!" aria-hidden="true">
          @for (i of $items(); track i) {
            <span class="skeleton aspect-[2/3] w-[clamp(112px,calc((100vw-56px)/2.5),160px)] flex-none"></span>
          }
        </div>
      }
      @case ('header') {
        <div class="flex flex-col gap-4" aria-hidden="true">
          <span class="skeleton aspect-video max-h-[40vh] w-full rounded-none"></span>
          <span class="flex flex-col gap-2 px-4">
            <span class="skeleton h-6 w-48"></span>
            <span class="skeleton h-4 w-32"></span>
          </span>
        </div>
      }
    }
  `,
  host: { role: 'status', class: 'block' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Skeleton {
  protected readonly translate = injectTranslator('app');

  readonly kind = input.required<'cards' | 'grid' | 'shelf' | 'header'>();
  readonly count = input(4);
  /** What screen readers hear, "Loading" by default. */
  readonly label = input<string | null>(null);

  protected readonly $items = computed(() => Array.from({ length: this.count() }, (_, i) => i));
}
