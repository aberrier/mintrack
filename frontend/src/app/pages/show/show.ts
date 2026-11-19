import { ChangeDetectionStrategy, Component, computed, inject, input, numberAttribute, signal } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { AuthStore } from '../../core/auth/auth.store';
import { formatDate } from '../../core/dates';
import { injectTranslator } from '../../core/i18n';
import { injectNotify } from '../../core/notify';
import {
  isAired,
  isWatched,
  LoadedSeasons,
  previousUnwatched,
  regularSeasonsBefore,
  seasonProgress,
  SPECIALS,
} from '../../core/tracking/episodes';
import { TrackingStore } from '../../core/tracking/tracking.store';
import { CHECKED_PAUSE_MS } from '../../core/tracking/watch-list.store';
import { BackButton } from '../../shared/back-button';
import { injectConfirm } from '../../shared/confirm-dialog';
import { CardEpisode, EpisodeCard, showEpisodeCard } from '../../shared/episode-card/episode-card';
import { LoadError } from '../../shared/load-error';
import { MediaHeader } from '../../shared/media-header';
import { loadMediaPage } from '../../shared/media-page';
import { Skeleton } from '../../shared/skeleton';
import { injectStatusLabel } from '../../shared/status';
import { SeasonRow } from './season-row';

type ShowTab = 'episodes' | 'about';

/**
 * A show: its header, then About (the overview and facts) or Episodes, where the next episode, each season and each
 * episode are marked in one tap. The next episode is the server's, guessed after a tap until the page loads again.
 */
@Component({
  selector: 'app-show',
  imports: [RouterLink, MatButton, EpisodeCard, MediaHeader, SeasonRow, Skeleton, LoadError, BackButton],
  templateUrl: './show.html',
  styleUrl: './show.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Show {
  private readonly store = inject(TrackingStore);
  private readonly notify = injectNotify();
  private readonly confirm = injectConfirm();
  protected readonly timeZone = inject(AuthStore).$timeZone;
  protected readonly translate = injectTranslator('app');
  protected readonly statusLabel = injectStatusLabel();
  protected readonly tabs: ShowTab[] = ['about', 'episodes'];
  protected readonly routes = appRoutes;
  protected readonly isWatched = isWatched;

  /** The `tmdbId` route parameter. */
  readonly tmdbId = input.required({ transform: numberAttribute });
  /** The `tab` query parameter: episodes unless it says about. */
  readonly tab = input<ShowTab, string | undefined>('episodes', {
    transform: (value) => (value === 'about' ? 'about' : 'episodes'),
  });

  protected readonly $show = computed(() => this.store.shows()[this.tmdbId()]);
  protected readonly page = loadMediaPage(this.tmdbId, (tmdbId) => this.store.loadShow(tmdbId), this.$show);
  /** The seasons loaded so far, by number. */
  protected readonly $episodes = computed((): LoadedSeasons => this.store.episodes()[this.tmdbId()] ?? {});
  /** Seasons open to their episodes, by number. */
  protected readonly $expanded = signal<ReadonlySet<number>>(new Set());
  /** Seasons whose episodes could not be loaded, by number. */
  protected readonly $failed = signal<ReadonlySet<number>>(new Set());
  /** Air dates are compared with the time the page opened. */
  protected readonly now = new Date();

  protected readonly $facts = computed(() => {
    const show = this.$show();
    if (!show) return [];
    const seasons = show.seasons.filter((season) => season.season_number !== SPECIALS).length;
    return [
      this.translate(seasons === 1 ? 'app.show.seasonsOne' : 'app.show.seasons', { count: String(seasons) }),
      show.network,
    ].filter((fact): fact is string => !!fact);
  });

  protected readonly $firstAired = computed(() => {
    const date = this.$show()?.release_date;
    return date ? formatDate(date, this.timeZone()) : null;
  });

  /** The Watch next card just checked, kept for a moment so the tap visibly registered before the next one. */
  private readonly $checked = signal<{ episode: Model.Http.Episode; card: CardEpisode } | null>(null);
  /** The episode to watch next and its card. */
  protected readonly $next = computed(() => {
    const checked = this.$checked();
    if (checked) return checked;
    const show = this.$show();
    const next = show?.next_episode;
    return next ? { episode: next, card: showEpisodeCard(show, next, next.remaining) } : null;
  });

  /** Open or close a season; its episodes load the first time it opens. */
  protected toggleSeason(season: Model.Http.Season): void {
    const number = season.season_number;
    const opening = !this.$expanded().has(number);
    this.$expanded.update((open) => {
      const next = new Set(open);
      if (!next.delete(number)) next.add(number);
      return next;
    });
    if (opening) this.loadSeason(number);
  }

  protected loadSeason(number: number): void {
    this.$failed.update((failed) => {
      const next = new Set(failed);
      next.delete(number);
      return next;
    });
    this.store
      .loadSeason(this.tmdbId(), number)
      .subscribe({ error: () => this.$failed.update((failed) => new Set(failed).add(number)) });
  }

  /** An episode's check: marks it, offering the earlier unwatched ones, or unmarks it. */
  protected tapEpisode(show: Model.Http.Show, episode: Model.Http.Episode): void {
    if (isWatched(show, episode)) {
      this.mark(show, [episode], false);
      return;
    }
    const previous = previousUnwatched(show, this.$episodes(), episode, this.now, this.timeZone());
    this.mark(show, [episode], true);
    if (previous === 0) return;
    this.notify(
      this.translate(previous === 1 ? 'app.show.previousOne' : 'app.show.previousMany', { count: String(previous) }),
      this.translate('app.common.markWatched'),
    )
      .onAction()
      .subscribe(() => this.markEarlier(episode));
  }

  /** Mark the aired episodes before `episode`, loading the earlier seasons not loaded yet. */
  private markEarlier(episode: Model.Http.Episode): void {
    const tmdbId = this.tmdbId();
    const seasons = regularSeasonsBefore(this.$show(), episode.season_number).map((season) => season.season_number);
    forkJoin([...seasons, episode.season_number].map((number) => this.store.loadSeason(tmdbId, number))).subscribe({
      next: (loaded) => {
        const current = this.$show();
        const earlier = loaded
          .flat()
          .filter(
            (other) =>
              (other.season_number < episode.season_number ||
                (other.season_number === episode.season_number && other.episode_number < episode.episode_number)) &&
              isAired(other, this.now, this.timeZone()) &&
              !isWatched(current, other),
          );
        this.mark(current, earlier, true);
      },
      error: () => this.notify(this.translate('app.tracking.saveFailed')),
    });
  }

  /** A season's check: marks its aired episodes, or, once they all are, unmarks the season after asking. */
  protected checkSeason(show: Model.Http.Show, season: Model.Http.Season): void {
    if (!seasonProgress(season).complete) {
      void this.store.markSeason(show.tmdb_id, season.season_number, true);
      return;
    }
    this.confirm({
      title: this.translate('app.show.unmarkTitle', { season: season.title }),
      message: this.translate('app.show.unmarkMessage'),
      confirm: this.translate('app.show.unmark'),
    }).subscribe(() => void this.store.markSeason(show.tmdb_id, season.season_number, false));
  }

  protected track(show: Model.Http.Show, status: Model.Http.ShowTrackingChoice): void {
    void this.store.trackShow(show.tmdb_id, status);
  }

  protected remove(show: Model.Http.Show): void {
    this.confirm({
      title: this.translate('app.show.removeTitle'),
      message: this.translate('app.show.removeMessage'),
      confirm: this.translate('app.common.remove'),
    }).subscribe(() => void this.store.untrackShow(show.tmdb_id));
  }

  /** Mark or unmark episodes; the store shows them at once, and throws confetti when the server says it is finished. */
  protected mark(show: Model.Http.Show, episodes: Model.Http.Episode[], watched: boolean): void {
    void this.store.setWatched(show.tmdb_id, episodes, watched);
  }

  /** Check the Watch next card: it stays checked for a moment, then the next episode rises in; taps meanwhile wait. */
  protected checkNext(show: Model.Http.Show): void {
    const next = this.$next();
    if (!next || this.$checked()) return;
    this.$checked.set(next);
    this.mark(show, [next.episode], true);
    setTimeout(() => this.$checked.set(null), CHECKED_PAUSE_MS);
  }
}
