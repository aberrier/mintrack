import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  Injectable,
  input,
  signal,
  Signal,
  WritableSignal,
} from '@angular/core';
import { MatIconButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { injectTranslator } from '../core/i18n';

export type ViewMode = 'list' | 'grid';

const STORAGE_PREFIX = 'mintrack.view.';

/**
 * The list or grid choice of each screen, remembered on this device. Storage may be unavailable (private browsing,
 * blocked site data): the choice then lasts until the app reloads.
 */
@Injectable({ providedIn: 'root' })
export class ViewModes {
  private readonly modes = new Map<string, WritableSignal<ViewMode>>();

  mode(key: string): Signal<ViewMode> {
    return this.modeFor(key).asReadonly();
  }

  set(key: string, mode: ViewMode): void {
    this.modeFor(key).set(mode);
    try {
      localStorage.setItem(STORAGE_PREFIX + key, mode);
    } catch {
      // Kept in memory only.
    }
  }

  private modeFor(key: string): WritableSignal<ViewMode> {
    let mode = this.modes.get(key);
    if (!mode) {
      mode = signal(readMode(key));
      this.modes.set(key, mode);
    }
    return mode;
  }
}

function readMode(key: string): ViewMode {
  try {
    return localStorage.getItem(STORAGE_PREFIX + key) === 'grid' ? 'grid' : 'list';
  } catch {
    return 'list';
  }
}

/** A button switching a screen between list and grid; its label says what a tap does. */
@Component({
  selector: 'app-view-toggle',
  imports: [MatIconButton, MatIcon],
  template: `
    <button
      matIconButton
      type="button"
      class="size-12!"
      [attr.aria-label]="translate($mode() === 'list' ? 'app.view.grid' : 'app.view.list')"
      (click)="toggle()"
      data-testid="view-toggle">
      <span class="icons" [class.grid]="$mode() === 'grid'">
        <mat-icon svgIcon="grid_view" aria-hidden="true" />
        <mat-icon svgIcon="view_agenda" aria-hidden="true" />
      </span>
    </button>
  `,
  /* Both icons share one cell: the one for the other view turns in as the current one turns out. */
  styles: `
    .icons {
      display: grid;
    }
    mat-icon {
      grid-area: 1 / 1;
      transition:
        opacity var(--duration-toggle) var(--ease-standard),
        transform var(--duration-medium) var(--ease-emph-decel);
    }
    .icons > :last-child,
    .icons.grid > :first-child {
      opacity: 0;
      transform: rotate(-90deg) scale(0.6);
    }
    .icons.grid > :last-child {
      opacity: 1;
      transform: none;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ViewToggle {
  protected readonly translate = injectTranslator('app');
  private readonly modes = inject(ViewModes);

  /** The screen whose choice this button changes. */
  readonly key = input.required<string>();

  protected readonly $mode = computed(() => this.modes.mode(this.key())());

  protected toggle(): void {
    this.modes.set(this.key(), this.$mode() === 'list' ? 'grid' : 'list');
  }
}
