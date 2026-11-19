import { injectTranslator, loadProfileTexts } from '../../../core/i18n';
import { durationText, monthBars } from './stats-format';

describe('stats format', () => {
  const translate = injectTranslator('app');

  beforeAll(async () => {
    await loadProfileTexts();
  });

  it('shows durations in days and hours, hours and minutes, or minutes', () => {
    expect(durationText(0, translate)).toBe('0m');
    expect(durationText(45, translate)).toBe('45m');
    expect(durationText(125, translate)).toBe('2h 5m');
    expect(durationText(3 * 1440 + 4 * 60 + 59, translate)).toBe('3d 4h');
  });

  it('scales the months to the busiest and names each one', () => {
    const bars = monthBars(
      [
        { month: '2025-12-01', episodes: 0, movies: 0 },
        { month: '2026-01-01', episodes: 6, movies: 2 },
        { month: '2026-02-01', episodes: 2, movies: 0 },
      ],
      translate,
    );

    expect(bars.map((bar) => [bar.initial, bar.episodes, bar.movies])).toEqual([
      ['D', 0, 0],
      ['J', 75, 25],
      ['F', 25, 0],
    ]);
    expect(bars[1]!.label).toBe('January 2026, episodes: 6, movies: 2');
  });
});
