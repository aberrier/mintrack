import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { formatDate } from '../../core/dates';
import { injectTranslator } from '../../core/i18n';
import { isUpcoming, isWatched, seasonProgress } from '../../core/tracking/episodes';
import { CheckButton } from '../../shared/check-button';
import { LoadError } from '../../shared/load-error';

/**
 * A season as one row: its title, `watched/aired` and a bar of the share watched, expanding to its episodes, and a
 * check marking its aired episodes in one tap. The episodes load when the season first opens and render only while it
 * is open: a long show has thousands.
 */
@Component({
  selector: 'app-season-row',
  imports: [MatIcon, CheckButton, LoadError],
  template: `
    @let s = season();
    @let progress = $progress();
    <div class="row">
      <button
        type="button"
        class="toggle state-layer"
        [attr.aria-expanded]="expanded()"
        [attr.aria-controls]="listId()"
        (click)="toggle.emit()">
        <span class="[font:var(--mat-sys-title-medium)]">{{ s.title }}</span>
        <mat-icon svgIcon="expand_more" class="chevron" [class.open]="expanded()" aria-hidden="true" />
        <span
          class="ms-auto text-on-surface-variant tabular-nums [font:var(--mat-sys-label-large)]"
          data-testid="season-progress"
          >{{ progress.watched }}/{{ progress.aired }}</span
        >
      </button>
      <button
        type="button"
        appCheckButton
        [done]="progress.complete"
        [disabled]="progress.aired === 0"
        [attr.aria-pressed]="progress.complete"
        [attr.aria-label]="translate('app.show.seasonCheck', { season: s.title })"
        (click)="check.emit()"></button>
    </div>
    <div class="bar" aria-hidden="true">
      <span [style.transform]="'scaleX(' + (progress.aired ? progress.watched / progress.aired : 0) + ')'"></span>
    </div>
    @if (expanded()) {
      @if (episodes(); as list) {
        <ul [id]="listId()">
          @for (episode of list; track episode.id) {
            @let watched = isWatched(show(), episode);
            <li class="episode enter" [style.--i]="$index">
              <div class="flex min-w-0 flex-col">
                <span class="truncate [font:var(--mat-sys-body-large)]">
                  <span class="tabular-nums">{{ episode.episode_number }}.</span> {{ episode.title }}
                </span>
                @if (episode.air_date) {
                  <span class="text-on-surface-variant [font:var(--mat-sys-body-medium)]">{{
                    formatDate(episode.air_date, timeZone())
                  }}</span>
                }
              </div>
              <button
                type="button"
                appCheckButton
                [done]="watched"
                [disabled]="!watched && isUpcoming(episode, now(), timeZone())"
                [attr.aria-pressed]="watched"
                [attr.aria-label]="s.title + ', ' + translate('app.show.episode') + ' ' + episode.episode_number"
                (click)="episodeTap.emit(episode)"
                data-testid="episode-toggle"></button>
            </li>
          }
        </ul>
      } @else if (failed()) {
        <app-load-error [id]="listId()" [message]="translate('app.show.seasonFailed')" (retry)="retry.emit()" />
      } @else {
        <p [id]="listId()" role="status" class="loading">{{ translate('app.common.loading') }}</p>
      }
    }
  `,
  styles: `
    :host {
      display: block;
      border-bottom: 1px solid var(--mat-sys-outline-variant);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-inline-end: 16px;
      padding-inline-end: 4px;
    }
    .toggle {
      display: flex;
      flex: 1;
      align-items: center;
      gap: 4px;
      min-width: 0;
      min-height: 64px;
      padding: 0 8px 0 16px;
      border: 0;
      background: none;
      color: var(--mat-sys-on-surface);
      text-align: start;
      cursor: pointer;
    }
    .chevron {
      color: var(--mat-sys-on-surface-variant);
      transition: transform var(--duration-medium) var(--ease-emph-decel);
    }
    .chevron.open {
      transform: rotate(180deg);
    }
    /* The share watched, as a thin bar under the row. */
    .bar {
      height: 4px;
      margin: 0 16px 12px;
      overflow: hidden;
      border-radius: var(--mat-sys-corner-full);
      background: var(--mat-sys-surface-container-high);
    }
    .bar > span {
      display: block;
      height: 100%;
      background: var(--mat-sys-primary);
      transform-origin: left;
      transition: transform var(--duration-medium) var(--ease-emph-decel);
    }
    ul {
      padding-bottom: 8px;
    }
    .loading {
      padding: 0 16px 16px;
      color: var(--mat-sys-on-surface-variant);
      font: var(--mat-sys-body-medium);
    }
    /* The season's episodes on a tinted card, their checks under the season's. */
    .episode {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      min-height: 64px;
      margin-inline: 16px;
      padding-inline: 16px 4px;
      background: var(--mat-sys-surface-container-low);
    }
    .episode:first-child {
      border-radius: var(--mat-sys-corner-large-top);
    }
    .episode:last-child {
      border-radius: 0 0 var(--mat-sys-corner-large) var(--mat-sys-corner-large);
    }
    .episode:only-child {
      border-radius: var(--mat-sys-corner-large);
    }
    .toggle:focus-visible {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -2px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SeasonRow {
  protected readonly translate = injectTranslator('app');
  protected readonly isWatched = isWatched;
  protected readonly isUpcoming = isUpcoming;
  protected readonly formatDate = formatDate;

  readonly show = input.required<Model.Http.Show>();
  readonly season = input.required<Model.Http.Season>();
  /** The season's episodes, once loaded. */
  readonly episodes = input<Model.Http.Episode[]>();
  /** Loading the episodes failed. */
  readonly failed = input(false);
  readonly expanded = input(false);
  /** Air dates are compared with this time, in the user's time zone. */
  readonly now = input.required<Date>();
  readonly timeZone = input.required<string>();

  readonly toggle = output<void>();
  /** The season's check was tapped. */
  readonly check = output<void>();
  readonly episodeTap = output<Model.Http.Episode>();
  /** Try loading the episodes again. */
  readonly retry = output<void>();

  protected readonly $progress = computed(() => seasonProgress(this.season()));
  protected readonly listId = computed(() => `season-${this.season().season_number}-episodes`);
}
