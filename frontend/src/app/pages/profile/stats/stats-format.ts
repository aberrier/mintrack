import { LOCALE } from '../../../core/dates';
import { AppTranslate } from '../../../core/i18n';

export { durationText, monthBars, type MonthBar };

const MINUTES_PER_DAY = 1440;

/** Minutes as days and hours ("3d 4h"), hours and minutes ("5h 12m") or minutes ("45m"). */
function durationText(total: number, translate: AppTranslate): string {
  const days = Math.floor(total / MINUTES_PER_DAY);
  const hours = Math.floor((total % MINUTES_PER_DAY) / 60);
  const minutes = String(total % 60);
  if (days) return translate('app.stats.duration.days', { days: String(days), hours: String(hours) });
  if (hours) return translate('app.stats.duration.hours', { hours: String(hours), minutes });
  return translate('app.stats.duration.minutes', { minutes });
}

interface MonthBar {
  /** The month's initial, under its bar. */
  initial: string;
  /** What a screen reader says of the month. */
  label: string;
  /** Heights in percent of the busiest month. */
  episodes: number;
  movies: number;
}

/** One bar per month, episodes stacked on movies, scaled to the busiest month. */
function monthBars(months: Model.Http.StatsMonth[], translate: AppTranslate): MonthBar[] {
  const busiest = Math.max(1, ...months.map((month) => month.episodes + month.movies));
  const name = (month: string, style: 'narrow' | 'long') =>
    new Intl.DateTimeFormat(LOCALE, {
      month: style,
      year: style === 'long' ? 'numeric' : undefined,
      timeZone: 'UTC',
    }).format(new Date(`${month}T00:00:00Z`));
  return months.map((month) => ({
    initial: name(month.month, 'narrow'),
    label: translate('app.stats.monthLabel', {
      month: name(month.month, 'long'),
      episodes: String(month.episodes),
      movies: String(month.movies),
    }),
    episodes: (month.episodes / busiest) * 100,
    movies: (month.movies / busiest) * 100,
  }));
}
