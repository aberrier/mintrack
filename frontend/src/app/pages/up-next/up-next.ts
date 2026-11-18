import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { tap } from 'rxjs';
import { ApiService } from '../../core/api/api.service';
import { injectTranslator } from '../../core/i18n';
import { EpisodeCard } from '../upcoming/episode-card';
import { UpcomingCache } from '../upcoming/upcoming-cache';

/** The next episode to watch of each show in progress, most recently active first. */
@Component({
  selector: 'app-up-next',
  imports: [EpisodeCard],
  templateUrl: './up-next.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class UpNext {
  protected readonly translate = injectTranslator('app');

  private readonly api = inject(ApiService);
  private readonly cache = inject(UpcomingCache).upNext;

  protected readonly upNext = rxResource({
    stream: () => this.api.upcoming.upNext().pipe(tap((response) => this.cache.set(response))),
  });

  /** The episodes, the last ones while loading, or undefined after an error (when reading the value would throw). */
  protected readonly episodes = computed(
    () => (this.upNext.hasValue() ? this.upNext.value() : this.upNext.error() ? undefined : this.cache())?.episodes,
  );
}
