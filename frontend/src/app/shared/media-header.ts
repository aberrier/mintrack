import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { backdropUrl } from '../core/tracking/episodes';

/**
 * The top of a show or movie page: the TMDB backdrop fading into the page, the title and a line of facts over its
 * bottom. A scrim from transparent to the page's surface keeps the text readable on any image, or on the plain tint
 * shown while there is none.
 */
@Component({
  selector: 'app-media-header',
  template: `
    @if ($url(); as url) {
      @if (!$failed()) {
        <img
          [src]="url"
          alt=""
          decoding="async"
          class="backdrop"
          [class.loaded]="$loaded()"
          (load)="$loaded.set(true)"
          (error)="$failed.set(true)" />
      }
    }
    <div class="text">
      <h1 class="[font:var(--mat-sys-headline-small)] font-semibold! text-balance">{{ title() }}</h1>
      @if (facts().length) {
        <p class="text-on-surface-variant [font:var(--mat-sys-body-medium)]" data-testid="media-facts">
          {{ facts().join(' · ') }}
        </p>
      }
    </div>
  `,
  styles: `
    :host {
      position: relative;
      display: flex;
      align-items: flex-end;
      min-height: 200px;
      aspect-ratio: 16 / 9;
      max-height: 40vh;
      overflow: hidden;
      background: var(--mat-sys-surface-container-high);
      color: var(--mat-sys-on-surface);
    }
    .backdrop {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      opacity: 0;
      transform: scale(1.04);
      transition:
        opacity 400ms var(--ease-standard),
        transform 600ms var(--ease-emph-decel);
    }
    .backdrop.loaded {
      opacity: 1;
      transform: none;
    }
    .text {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 4px;
      width: 100%;
      padding: 64px 16px 16px;
      background: linear-gradient(
        transparent,
        color-mix(in srgb, var(--mat-sys-surface) 80%, transparent) 50%,
        var(--mat-sys-surface)
      );
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MediaHeader {
  readonly title = input.required<string>();
  readonly backdropPath = input.required<string | null>();
  /** Shown under the title, joined by dots: seasons and network, or runtime and release date. */
  readonly facts = input<string[]>([]);

  protected readonly $url = computed(() => backdropUrl(this.backdropPath()));
  protected readonly $loaded = signal(false);
  protected readonly $failed = signal(false);
}
