import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { posterUrl } from '../core/tracking/episodes';

/** A TMDB poster at its 2:3 ratio, on a plain surface while it loads or when there is none. */
@Component({
  selector: 'app-poster',
  template: `
    <div class="aspect-[2/3] w-full overflow-hidden rounded-lg bg-[var(--mat-sys-surface-container-high)]">
      @if ($url(); as url) {
        <img [src]="url" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover" />
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Poster {
  readonly path = input.required<string | null>();
  readonly width = input<'w185' | 'w342'>('w185');

  protected readonly $url = computed(() => posterUrl(this.path(), this.width()));
}
