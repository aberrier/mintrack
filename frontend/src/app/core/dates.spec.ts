import { dayIn, formatDate, formatDay, formatMonth, formatTime } from './dates';

// A Wednesday.
const NOW = new Date('2026-11-18T12:00:00Z');
const TODAY = '2026-11-18';

describe('dates', () => {
  it('formats a date without the year this year, with it another year', () => {
    expect(formatDate('2026-05-01', 'UTC', NOW)).toBe('1 May');
    expect(formatDate('2020-05-01', 'UTC', NOW)).toBe('1 May 2020');
  });

  it('reads an instant in the user time zone and a plain day as it is', () => {
    // 23:30 UTC on 31 December is already New Year's Day in Paris.
    expect(formatDate('2025-12-31T23:30:00Z', 'Europe/Paris', NOW)).toBe('1 Jan');
    expect(formatDate('2026-01-01', 'Pacific/Honolulu', NOW)).toBe('1 Jan');
    expect(dayIn('Pacific/Auckland', NOW)).toBe('2026-11-19');
  });

  it('names a coming day by its weekday until Sunday, then by its date', () => {
    expect(formatDay('2026-11-20', TODAY)).toBe('Friday');
    expect(formatDay('2026-11-22', TODAY)).toBe('Sunday');
    expect(formatDay('2026-11-23', TODAY)).toBe('23 November');
    expect(formatDay('2027-01-05', TODAY)).toBe('5 January 2027');
  });

  it('names months and times in English whatever the device language', () => {
    expect(formatMonth('2026-12-01', TODAY)).toBe('December');
    expect(formatMonth('2027-01-01', TODAY)).toBe('January 2027');
    expect(formatTime('2026-11-18T20:00:00Z', 'UTC')).toBe('20:00');
  });
});
