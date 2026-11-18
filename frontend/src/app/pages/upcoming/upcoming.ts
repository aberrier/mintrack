import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { tap } from 'rxjs';
import { ApiService } from '../../core/api/api.service';
import { injectTranslator } from '../../core/i18n';
import { dayIn, formatDay, formatTime, nextDay } from './air-time';
import { EpisodeCard } from './episode-card';
import { UpcomingCache } from './upcoming-cache';

/** The new episodes, then those airing over the coming weeks, by day in the user's time zone. */
@Component({
  selector: 'app-upcoming',
  imports: [EpisodeCard],
  templateUrl: './upcoming.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Upcoming {
  protected readonly translate = injectTranslator('app');

  private readonly api = inject(ApiService);
  private readonly cache = inject(UpcomingCache).upcoming;

  protected readonly upcoming = rxResource({
    stream: () => this.api.upcoming.get().pipe(tap((response) => this.cache.set(response))),
  });

  /** The response, the last one while loading, or undefined after an error (when reading the value would throw). */
  private readonly response = computed(() =>
    this.upcoming.hasValue() ? this.upcoming.value() : this.upcoming.error() ? undefined : this.cache(),
  );

  protected readonly newEpisodes = computed(() =>
    (this.response()?.new ?? []).map((episode) => ({
      episode,
      detail: episode.day ? formatDay(episode.day, 'short') : null,
    })),
  );

  protected readonly days = computed(() => {
    const upcoming = this.response();
    if (!upcoming) return [];
    const today = dayIn(upcoming.time_zone);
    const tomorrow = nextDay(today);
    return upcoming.days.map(({ day, episodes }) => ({
      day,
      label:
        day === today
          ? this.translate('app.upcoming.today')
          : day === tomorrow
            ? this.translate('app.upcoming.tomorrow')
            : formatDay(day),
      episodes: episodes.map((episode) => ({
        episode,
        detail: episode.airstamp ? formatTime(episode.airstamp, upcoming.time_zone) : null,
      })),
    }));
  });

  protected readonly isEmpty = computed(() => this.newEpisodes().length === 0 && this.days().length === 0);
}
