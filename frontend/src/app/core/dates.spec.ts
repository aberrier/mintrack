import {
  dayIn,
  formatDate,
  formatDay,
  formatMonth,
  formatTime,
  localDateTime,
  zonedInstant,
  zoneWithOffset,
} from './dates';

// A Wednesday.
const NOW = new Date('2026-11-18T12:00:00Z');
const TODAY = '2026-11-18';

describe('dates', () => {
  it('names a time zone with its offset from GMT at that time', () => {
    expect(zoneWithOffset('Europe/Paris', NOW)).toBe('Europe/Paris (GMT+1)');
    expect(zoneWithOffset('Europe/Paris', new Date('2026-07-01T12:00:00Z'))).toBe('Europe/Paris (GMT+2)');
    expect(zoneWithOffset('America/St_Johns', NOW)).toBe('America/St_Johns (GMT-3:30)');
    expect(zoneWithOffset('UTC', NOW)).toBe('UTC (GMT+0)');
  });

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

  it('turns an instant into a date-time input value in a time zone and back', () => {
    expect(localDateTime(new Date('2025-12-31T23:30:00Z'), 'Europe/Paris')).toBe('2026-01-01T00:30');
    expect(zonedInstant('2026-01-01T00:30', 'Europe/Paris').toISOString()).toBe('2025-12-31T23:30:00.000Z');
    // Summer time in Paris, and the other side of the date line.
    expect(zonedInstant('2026-07-01T20:00', 'Europe/Paris').toISOString()).toBe('2026-07-01T18:00:00.000Z');
    expect(zonedInstant('2026-11-19T09:00', 'Pacific/Auckland').toISOString()).toBe('2026-11-18T20:00:00.000Z');
  });
});
