import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { MAT_BOTTOM_SHEET_DATA, MatBottomSheet, MatBottomSheetRef } from '@angular/material/bottom-sheet';
import { MatFormField, MatLabel } from '@angular/material/form-field';
import { MatIcon } from '@angular/material/icon';
import { MatInput } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../app.paths';
import { ApiService } from '../core/api/api.service';
import { AuthStore } from '../core/auth/auth.store';
import { formatDate, formatDateTime, localDateTime, zonedInstant } from '../core/dates';
import { injectTranslator } from '../core/i18n';
import { injectNotify } from '../core/notify';
import { isAired, isUpcoming } from '../core/tracking/episodes';
import { TrackingStore } from '../core/tracking/tracking.store';
import { WatchListStore } from '../core/tracking/watch-list.store';
import { CheckButton } from './check-button';
import { imageUrl } from './images';
import { LoadError } from './load-error';
import { RatingForm } from './rating-form';

interface EpisodeSheetData {
  episodeId: string;
}

/**
 * An episode in a bottom sheet: its still, number and title, a link to its show, its synopsis, air date, network and
 * TMDB score, then the user's watch (marked or not, its date changeable) and their own rating.
 */
@Component({
  selector: 'app-episode-sheet',
  imports: [RouterLink, MatIcon, MatFormField, MatLabel, MatInput, CheckButton, LoadError, RatingForm],
  template: `
    @if (episode.hasValue()) {
      @let ep = episode.value();
      <article class="flex flex-col gap-6 pb-4" data-testid="episode-sheet">
        @if ($still(); as still) {
          <img class="still" [src]="still" alt="" decoding="async" />
        }
        <header class="flex flex-col items-start gap-1">
          <a
            class="show-link"
            [routerLink]="routes.show(ep.tmdb_id)"
            [attr.aria-label]="translate('app.episodeSheet.openShow', { show: ep.show_title })"
            (click)="ref.dismiss()"
            >{{ ep.show_title }}</a
          >
          <h2 class="[font:var(--mat-sys-headline-small)] text-balance" data-testid="sheet-title">
            <span class="tabular-nums">{{ $code() }}</span> {{ ep.title }}
          </h2>
          @if ($facts(); as facts) {
            <p class="text-on-surface-variant [font:var(--mat-sys-body-medium)]" data-testid="sheet-facts">
              {{ facts }}
            </p>
          }
          @if (ep.vote_count && ep.vote_average !== null) {
            <p
              class="score"
              data-testid="sheet-tmdb-score"
              [attr.aria-label]="
                translate('app.rating.tmdbScore', { score: ep.vote_average.toFixed(1), votes: '' + ep.vote_count })
              ">
              <mat-icon svgIcon="star_fill" aria-hidden="true" />
              <span aria-hidden="true"
                >{{ ep.vote_average.toFixed(1) }}
                <span class="text-on-surface-variant">· TMDB ({{ ep.vote_count }})</span></span
              >
            </p>
          }
        </header>

        @if (ep.overview) {
          <p class="max-w-[65ch] [font:var(--mat-sys-body-large)]" data-testid="sheet-overview">{{ ep.overview }}</p>
        }

        <section class="flex flex-col gap-2">
          <div class="watched">
            <p class="flex-1 [font:var(--mat-sys-title-medium)]" data-testid="sheet-watched">
              {{
                $watchedOn()
                  ? translate('app.episodeSheet.watchedOn', { date: $watchedOn()! })
                  : translate('app.episodeSheet.notWatched')
              }}
            </p>
            <button
              type="button"
              appCheckButton
              [done]="$watchedAt() !== null"
              [disabled]="$watchedAt() === null && $upcoming()"
              [attr.aria-pressed]="$watchedAt() !== null"
              [attr.aria-label]="translate('app.common.markWatched')"
              (click)="toggle(ep)"></button>
          </div>
          @if ($watchedAt(); as watchedAt) {
            <mat-form-field subscriptSizing="dynamic">
              <mat-label>{{ translate('app.episodeSheet.watchedAt') }}</mat-label>
              <input
                matInput
                type="datetime-local"
                [value]="local(watchedAt)"
                [max]="local(now)"
                (change)="changeDate(ep, $any($event.target).value)" />
            </mat-form-field>
          }
        </section>

        <app-rating-form [path]="'episodes/' + ep.id" [rating]="$rating()" (saved)="rated(ep, $event)" />
      </article>
    } @else if (episode.error()) {
      <app-load-error [message]="translate('app.episodeSheet.loadFailed')" (retry)="episode.reload()" />
    } @else {
      <p role="status" class="py-8 text-on-surface-variant">{{ translate('app.common.loading') }}</p>
    }
  `,
  host: { class: 'block' },
  styles: `
    .still {
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border-radius: var(--mat-sys-corner-large);
      background: var(--mat-sys-surface-container-high);
    }
    /* The show's name as a link, a 48px target sized to its text. */
    .show-link {
      display: inline-flex;
      align-items: center;
      min-height: 48px;
      margin-block: -12px;
      color: var(--mat-sys-primary);
      font: var(--mat-sys-label-large);
      text-decoration: none;
    }
    .show-link:focus-visible {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: 2px;
    }
    .score {
      display: flex;
      align-items: center;
      gap: 4px;
      font: var(--mat-sys-label-large);
      font-variant-numeric: tabular-nums;
    }
    .score mat-icon {
      width: 20px;
      height: 20px;
      color: var(--mat-sys-primary);
    }
    /* Whether the episode is watched, on a card a tone above the sheet with its check, as on a movie's page. */
    .watched {
      display: flex;
      align-items: center;
      gap: 16px;
      min-height: 64px;
      padding: 8px 4px 8px 16px;
      border-radius: var(--mat-sys-corner-large);
      background: var(--mat-sys-surface-container-high);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EpisodeSheet {
  private readonly api = inject(ApiService);
  private readonly tracking = inject(TrackingStore);
  private readonly watchList = inject(WatchListStore);
  private readonly notify = injectNotify();
  private readonly timeZone = inject(AuthStore).$timeZone;
  private readonly data = inject<EpisodeSheetData>(MAT_BOTTOM_SHEET_DATA);
  protected readonly ref = inject(MatBottomSheetRef);
  protected readonly translate = injectTranslator('app');
  protected readonly routes = appRoutes;
  /** Air dates and watch dates are compared with the time the sheet opened. */
  protected readonly now = new Date();

  protected readonly episode = rxResource({ stream: () => this.api.episodes.get(this.data.episodeId) });
  private readonly $episode = computed(() => (this.episode.hasValue() ? this.episode.value() : undefined));

  /** The user's watch, changed here at once and put back if the server refuses. */
  protected readonly $watchedAt = linkedSignal(() => this.$episode()?.watched_at ?? null);
  protected readonly $rating = linkedSignal(() => this.$episode()?.rating ?? null);

  protected readonly $still = computed(() => imageUrl(this.$episode()?.still_path ?? null, 'w300'));
  protected readonly $code = computed(() => {
    const ep = this.$episode();
    const pad = (value: number) => String(value).padStart(2, '0');
    return ep ? `S${pad(ep.season_number)}E${pad(ep.episode_number)}` : '';
  });
  protected readonly $upcoming = computed(() => {
    const ep = this.$episode();
    return !!ep && isUpcoming(ep, this.now, this.timeZone());
  });
  /** "Aired 13 Nov 2025 · Network". */
  protected readonly $facts = computed(() => {
    const ep = this.$episode();
    if (!ep) return null;
    const date = ep.airstamp ?? ep.air_date;
    const aired = date
      ? this.translate(isAired(ep, this.now, this.timeZone()) ? 'app.episodeSheet.aired' : 'app.episodeSheet.airs', {
          date: formatDate(date, this.timeZone()),
        })
      : null;
    return [aired, ep.network].filter(Boolean).join(' · ') || null;
  });
  protected readonly $watchedOn = computed(() => {
    const watchedAt = this.$watchedAt();
    return watchedAt ? formatDateTime(watchedAt, this.timeZone()) : null;
  });

  protected local(instant: string | Date): string {
    return localDateTime(new Date(instant), this.timeZone());
  }

  /** The check: marked watched now, or unmarked. */
  protected async toggle(ep: Model.Http.EpisodeDetail): Promise<void> {
    const before = this.$watchedAt();
    const watched = before === null;
    const after = watched ? new Date().toISOString() : null;
    this.$watchedAt.set(after);
    if (!(await this.tracking.setWatched(ep.tmdb_id, [ep], watched))) {
      this.$watchedAt.set(before);
      return;
    }
    this.watchList.episodeChanged(ep.id, { watched_at: after });
  }

  /** A date picked for the watch: saved unless it is after now. */
  protected async changeDate(ep: Model.Http.EpisodeDetail, local: string): Promise<void> {
    const before = this.$watchedAt();
    if (!local || !before) return;
    const at = zonedInstant(local, this.timeZone());
    if (at > new Date()) {
      this.notify(this.translate('app.episodeSheet.future'));
      return;
    }
    const watchedAt = at.toISOString();
    this.$watchedAt.set(watchedAt);
    if (!(await this.tracking.setWatchedAt(ep.tmdb_id, ep.id, watchedAt))) {
      this.$watchedAt.set(before);
      return;
    }
    this.notify(this.translate('app.episodeSheet.dateSaved'));
    this.watchList.episodeChanged(ep.id, { watched_at: watchedAt });
  }

  protected rated(ep: Model.Http.EpisodeDetail, rating: Model.Http.Rating | null): void {
    this.$rating.set(rating);
    this.watchList.episodeChanged(ep.id, { rating: rating?.stars ?? null });
  }
}

/** Open an episode's sheet by its id. */
export function injectEpisodeSheet(): (episodeId: string) => void {
  const sheet = inject(MatBottomSheet);
  const translate = injectTranslator('app');
  return (episodeId) => {
    sheet.open<EpisodeSheet, EpisodeSheetData>(EpisodeSheet, {
      data: { episodeId },
      ariaLabel: translate('app.episodeSheet.label'),
    });
  };
}
