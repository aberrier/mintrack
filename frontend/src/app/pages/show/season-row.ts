import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { injectTranslator } from '../../core/i18n';
import { isUpcoming, isWatched, seasonProgress, SPECIALS } from '../../core/tracking/episodes';
import { CheckMark } from '../../shared/check-mark';

/**
 * A season as one row: its title and `watched/aired`, expanding to its episodes, and a check marking its aired
 * episodes in one tap. The episodes render only while the season is open: a long show has thousands.
 */
@Component({
  selector: 'app-season-row',
  imports: [MatIcon, CheckMark],
  template: `
    @let s = season();
    @let progress = $progress();
    <div class="row">
      <button
        type="button"
        class="toggle"
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
      @if (s.season_number !== specials) {
        <button
          type="button"
          class="check"
          [class.done]="progress.complete"
          [disabled]="progress.aired === 0"
          [attr.aria-pressed]="progress.complete"
          [attr.aria-label]="translate('app.show.seasonCheck', { season: s.title })"
          (click)="check.emit()">
          <app-check-mark [done]="progress.complete" />
        </button>
      }
    </div>
    @if (expanded()) {
      <ul [id]="listId()">
        @for (episode of s.episodes; track episode.id) {
          @let watched = isWatched(show(), episode);
          <li class="episode enter" [style.--i]="$index">
            <div class="flex min-w-0 flex-col">
              <span class="truncate [font:var(--mat-sys-body-large)]">
                <span class="tabular-nums">{{ episode.episode_number }}.</span> {{ episode.title }}
              </span>
              @if (episode.air_date) {
                <span class="text-on-surface-variant [font:var(--mat-sys-body-small)]">{{ episode.air_date }}</span>
              }
            </div>
            <button
              type="button"
              class="check"
              [class.done]="watched"
              [disabled]="!watched && isUpcoming(episode, now())"
              [attr.aria-pressed]="watched"
              [attr.aria-label]="s.title + ', ' + translate('app.show.episode') + ' ' + episode.episode_number"
              (click)="episodeTap.emit(episode)"
              data-testid="episode-toggle">
              <app-check-mark [done]="watched" />
            </button>
          </li>
        }
      </ul>
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
    ul {
      padding-bottom: 8px;
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
      border-radius: 16px 16px 0 0;
    }
    .episode:last-child {
      border-radius: 0 0 16px 16px;
    }
    .episode:only-child {
      border-radius: 16px;
    }
    /* A 48px target around the 36px mark. */
    .check {
      display: grid;
      flex: none;
      place-items: center;
      width: 48px;
      height: 48px;
      padding: 0;
      border: 0;
      background: none;
      cursor: pointer;
    }
    .check:active app-check-mark {
      transform: scale(0.9);
    }
    app-check-mark {
      transition: transform var(--duration-short) var(--ease-standard);
    }
    .check:disabled {
      opacity: 0.38;
      cursor: default;
    }
    .toggle:focus-visible,
    .check:focus-visible {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -2px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SeasonRow {
  protected readonly translate = injectTranslator('app');
  protected readonly specials = SPECIALS;
  protected readonly isWatched = isWatched;
  protected readonly isUpcoming = isUpcoming;

  readonly show = input.required<Model.Http.Show>();
  readonly season = input.required<Model.Http.Season>();
  readonly expanded = input(false);
  /** Air dates are compared with this time. */
  readonly now = input.required<Date>();

  readonly toggle = output<void>();
  /** The season's check was tapped. */
  readonly check = output<void>();
  readonly episodeTap = output<Model.Http.Episode>();

  protected readonly $progress = computed(() => seasonProgress(this.show(), this.season(), this.now()));
  protected readonly listId = computed(() => `season-${this.season().season_number}-episodes`);
}
