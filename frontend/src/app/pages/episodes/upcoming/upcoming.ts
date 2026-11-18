import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { tap } from 'rxjs';
import { ApiService } from '../../../core/api/api.service';
import { dayIn, formatDay, formatMonth, formatTime, nextDay } from '../../../core/dates';
import { injectTranslator } from '../../../core/i18n';
import { EmptyState } from '../../../shared/empty-state';
import { EpisodeCard } from '../../../shared/episode-card/episode-card';
import { LoadError } from '../../../shared/load-error';
import { Skeleton } from '../../../shared/skeleton';
import { ViewModes } from '../../../shared/view-toggle';
import { EpisodesTabs } from '../episodes-tabs';
import { UpcomingCache } from './upcoming-cache';

/**
 * The episodes airing from today over the coming weeks, by day in the user's time zone: Today, Tomorrow, the
 * weekdays until Sunday, then dates, with the month's name where a new month starts.
 */
@Component({
  selector: 'app-upcoming',
  imports: [EpisodeCard, EpisodesTabs, EmptyState, Skeleton, LoadError],
  templateUrl: './upcoming.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Upcoming {
  protected readonly translate = injectTranslator('app');
  protected readonly $mode = inject(ViewModes).mode('upcoming');

  private readonly api = inject(ApiService);
  private readonly cache = inject(UpcomingCache).upcoming;

  protected readonly upcoming = rxResource({
    stream: () => this.api.upcoming.get().pipe(tap((response) => this.cache.set(response))),
  });

  /** The response, the last one while loading, or undefined after an error (when reading the value would throw). */
  private readonly response = computed(() =>
    this.upcoming.hasValue() ? this.upcoming.value() : this.upcoming.error() ? undefined : this.cache(),
  );

  protected readonly days = computed(() => {
    const upcoming = this.response();
    if (!upcoming) return [];
    const today = dayIn(upcoming.time_zone);
    const tomorrow = nextDay(today);
    let month = today.slice(0, 7);
    return upcoming.days.map(({ day, episodes }) => {
      const newMonth = day.slice(0, 7) !== month;
      month = day.slice(0, 7);
      return {
        day,
        month: newMonth ? formatMonth(day, today) : null,
        label:
          day === today
            ? this.translate('app.upcoming.today')
            : day === tomorrow
              ? this.translate('app.upcoming.tomorrow')
              : formatDay(day, today),
        episodes: episodes.map((episode) => ({
          episode,
          detail: episode.airstamp ? formatTime(episode.airstamp, upcoming.time_zone) : null,
        })),
      };
    });
  });
}
