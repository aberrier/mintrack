import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { injectTranslator } from '../core/i18n';
import { posterUrl } from '../core/tracking/episodes';

/**
 * A TMDB poster at its 2:3 ratio, fading in over a plain surface once loaded; the surface stays when there is none or
 * it fails. It can carry a Finished badge, and an add button (`+`, then a check once in the library) that emits `add`:
 * a poster with that button must not sit inside a link, but a link stretched over it from a sibling stays under the
 * button.
 */
@Component({
  selector: 'app-poster',
  imports: [MatIcon],
  template: `
    <div class="frame">
      @if ($url(); as url) {
        @if (!$failed()) {
          <img
            [src]="url"
            alt=""
            loading="lazy"
            decoding="async"
            [class.loaded]="$loaded()"
            (load)="$loaded.set(true)"
            (error)="$failed.set(true)" />
        }
      }
      @if (finished()) {
        <span class="badge" data-testid="finished-badge">
          <mat-icon svgIcon="check_circle_fill" aria-hidden="true" />{{ translate('app.poster.finished') }}
        </span>
      }
    </div>
    @if (tracked() !== null) {
      <button
        type="button"
        class="add"
        [class.done]="tracked()"
        [attr.aria-label]="translate(tracked() ? 'app.poster.added' : 'app.poster.add', { title: label() })"
        [attr.aria-disabled]="tracked() ? 'true' : null"
        (click)="tracked() || add.emit()">
        <span class="square">
          <mat-icon svgIcon="add" class="plus" aria-hidden="true" />
          <mat-icon svgIcon="check" class="tick" aria-hidden="true" />
        </span>
      </button>
    }
  `,
  styles: `
    :host {
      position: relative;
      display: block;
    }
    .frame {
      position: relative;
      aspect-ratio: 2 / 3;
      width: 100%;
      overflow: hidden;
      border-radius: 8px;
      background: var(--mat-sys-surface-container-high);
    }
    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      opacity: 0;
      transition: opacity var(--duration-medium) var(--ease-standard);
    }
    img.loaded {
      opacity: 1;
    }
    .badge {
      position: absolute;
      inset: auto 4px 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      padding: 2px 4px;
      border-radius: 4px;
      background: var(--mat-sys-primary);
      color: var(--mat-sys-on-primary);
      font: var(--mat-sys-label-medium);
    }
    .badge mat-icon {
      width: 16px;
      height: 16px;
    }
    /* A 48px target in the corner, drawn as a 28px square, above a link stretched over the poster. */
    .add {
      position: absolute;
      top: 0;
      right: 0;
      z-index: 1;
      display: grid;
      place-items: center;
      width: 48px;
      height: 48px;
      padding: 0;
      border: 0;
      background: none;
      cursor: pointer;
    }
    .square {
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 8px;
      background: color-mix(in srgb, var(--mat-sys-surface) 85%, transparent);
      color: var(--mat-sys-on-surface);
      transition:
        background-color var(--duration-toggle) var(--ease-standard),
        transform var(--duration-short) var(--ease-standard);
    }
    .add:active .square {
      transform: scale(0.9);
    }
    .square mat-icon {
      grid-area: 1 / 1;
      width: 20px;
      height: 20px;
      transition:
        opacity var(--duration-toggle) var(--ease-standard),
        transform var(--duration-medium) var(--ease-pop);
    }
    .tick {
      opacity: 0;
      transform: rotate(-45deg) scale(0.5);
    }
    .add.done .square {
      background: var(--mat-sys-primary);
      color: var(--mat-sys-on-primary);
    }
    .add.done .plus {
      opacity: 0;
      transform: rotate(45deg) scale(0.5);
    }
    .add.done .tick {
      opacity: 1;
      transform: none;
    }
    .add:focus-visible {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -4px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Poster {
  protected readonly translate = injectTranslator('app');

  readonly path = input.required<string | null>();
  readonly width = input<'w185' | 'w342'>('w185');
  /** Shows the Finished badge. */
  readonly finished = input(false);
  /** null: no add button; false: `+`; true: a check, in the library. */
  readonly tracked = input<boolean | null>(null);
  /** Names the add button. */
  readonly label = input('');

  readonly add = output<void>();

  protected readonly $url = computed(() => posterUrl(this.path(), this.width()));
  protected readonly $loaded = signal(false);
  protected readonly $failed = signal(false);
}
