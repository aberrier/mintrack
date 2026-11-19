import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { appRoutes } from '../../../app.paths';
import { ApiService } from '../../../core/api/api.service';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { BackButton } from '../../../shared/back-button';
import { EmptyState } from '../../../shared/empty-state';
import { LoadError } from '../../../shared/load-error';
import { durationText, monthBars } from './stats-format';

/**
 * The user's own figures: time spent watching, totals, streaks, the last twelve months as bars, and top genres and
 * networks with bars relative to the first.
 */
@Component({
  selector: 'app-stats',
  imports: [BackButton, EmptyState, LoadError],
  templateUrl: './stats.html',
  styles: `
    .panel {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-inline: 16px;
      padding: 16px;
      border-radius: var(--mat-sys-corner-large);
      background: var(--mat-sys-surface-container-low);
    }
    .figure {
      font: var(--mat-sys-headline-small);
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    .chart {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 4px;
      align-items: end;
    }
    .column {
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      height: 128px;
    }
    .bar {
      min-height: 2px;
      border-radius: var(--mat-sys-corner-extra-small);
    }
    .episodes {
      background: var(--mat-sys-primary);
    }
    /* Apart from the episodes by hue, and at least 3:1 against the surface in both schemes. */
    .movies {
      background: var(--mat-sys-tertiary);
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: var(--mat-sys-corner-full);
    }
    .track {
      height: 8px;
      border-radius: var(--mat-sys-corner-full);
      background: var(--mat-sys-surface-container-highest);
    }
    .track > span {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: var(--mat-sys-primary);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Stats {
  private readonly api = inject(ApiService);
  protected readonly translate = injectTranslator('app');
  protected readonly routes = appRoutes;

  protected readonly stats = rxResource({ stream: () => this.api.stats() });

  protected readonly $view = computed(() => {
    const stats = this.stats.value();
    if (!stats) return null;
    const duration = (minutes: number) => durationText(minutes, this.translate);
    return {
      stats,
      empty: stats.episodes + stats.movies === 0,
      total: duration(stats.episode_minutes + stats.movie_minutes),
      episodeTime: duration(stats.episode_minutes),
      movieTime: duration(stats.movie_minutes),
      notCounted: stats.episodes_without_runtime + stats.movies_without_runtime,
      totals: [
        { label: this.translate('app.stats.shows'), value: stats.shows },
        { label: this.translate('app.stats.finishedShows'), value: stats.finished_shows },
        { label: this.translate('app.stats.episodes'), value: stats.episodes },
        { label: this.translate('app.stats.movies'), value: stats.movies },
      ],
      months: monthBars(stats.months, this.translate),
      rankings: [
        { id: 'genres', title: this.translate('app.stats.genres'), rows: this.ranked(stats.genres, 'titles') },
        { id: 'networks', title: this.translate('app.stats.networks'), rows: this.ranked(stats.networks, 'shows') },
      ].filter((ranking) => ranking.rows.length),
    };
  });

  protected days(count: number): string {
    return count === 1
      ? this.translate('app.stats.oneDay')
      : this.translate('app.stats.days', { count: String(count) });
  }

  private ranked(items: Model.Http.StatsRanked[], unit: 'titles' | 'shows') {
    const first = Math.max(1, ...items.map((item) => item.titles));
    const [one, many]: TranslationPath<'app'>[] =
      unit === 'titles' ? ['app.stats.oneTitle', 'app.stats.titles'] : ['app.stats.oneShow', 'app.stats.showsCount'];
    return items.map((item) => ({
      name: item.name,
      count: item.titles === 1 ? this.translate(one) : this.translate(many, { count: String(item.titles) }),
      width: (item.titles / first) * 100,
    }));
  }
}
