import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Poster } from './poster';

/**
 * A show or a movie in a grid or a row: its poster and title, the whole tile opening its page. The title's link is
 * stretched over the tile, so the poster's add button stays a separate control on top of it.
 */
@Component({
  selector: 'app-media-tile',
  imports: [RouterLink, Poster],
  template: `
    <app-poster
      [path]="posterPath()"
      [finished]="finished()"
      [tracked]="tracked()"
      [label]="title()"
      (add)="add.emit()" />
    <a [routerLink]="link()" class="title">{{ title() }}</a>
    @if (detail(); as text) {
      <span class="text-on-surface-variant [font:var(--mat-sys-body-small)] tabular-nums" data-testid="tile-detail">{{
        text
      }}</span>
    }
  `,
  styles: `
    :host {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    app-poster {
      margin-bottom: 4px;
      transition: transform var(--duration-short) var(--ease-standard);
    }
    /* The tile sinks a little while its link is pressed. */
    :host:has(.title:active) app-poster {
      transform: scale(0.97);
    }
    /* Two lines at most, in a 48px target of its own besides the poster's. */
    .title {
      display: -webkit-box;
      min-height: 48px;
      overflow: hidden;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      color: inherit;
      font: var(--mat-sys-title-small);
      text-decoration: none;
    }
    .title::after {
      content: '';
      position: absolute;
      inset: 0;
      border-radius: 8px;
    }
    .title:focus-visible {
      outline: none;
    }
    .title:focus-visible::after {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: 2px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MediaTile {
  readonly link = input.required<string>();
  readonly title = input.required<string>();
  readonly posterPath = input.required<string | null>();
  readonly finished = input(false);
  /** null: no add button; false: `+`; true: a check, in the library. */
  readonly tracked = input<boolean | null>(null);
  /** A line under the title, such as the progress. */
  readonly detail = input<string | null>(null);

  readonly add = output<void>();
}
