/**
 * Days and times as the app shows them, always in the user's time zone and in the app's English, whatever the device's
 * language. A day (YYYY-MM-DD) has no zone of its own: it is formatted as is.
 */
export {
  LOCALE,
  browserTimeZone,
  dayIn,
  formatDate,
  formatDateTime,
  formatDay,
  formatMonth,
  formatTime,
  nextDay,
  zoneWithOffset,
};

/** The app's texts are English: dates read "24 November", "Tuesday". */
const LOCALE = 'en-GB';
const DAY_MS = 86_400_000;

/** The time zone this device is set to, such as "Europe/Paris". */
function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** The calendar day (YYYY-MM-DD) of an instant in a time zone. */
function dayIn(timeZone: string, instant = new Date()): string {
  const parts = new Intl.DateTimeFormat(LOCALE, { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .formatToParts(instant)
    .reduce<Record<string, string>>((found, part) => ({ ...found, [part.type]: part.value }), {});
  return `${parts['year']}-${parts['month']}-${parts['day']}`;
}

/** The day (YYYY-MM-DD) after a day. */
function nextDay(day: string): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + DAY_MS).toISOString().slice(0, 10);
}

/** Days from `from` to `to`, both YYYY-MM-DD. */
function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

/** An ISO day or date-time as an instant and the zone to read it in. */
function parse(iso: string, timeZone: string): { date: Date; zone: string } {
  return iso.length === 10
    ? { date: new Date(`${iso}T00:00:00Z`), zone: 'UTC' }
    : { date: new Date(iso), zone: timeZone };
}

/** A date such as "13 Nov", with the year when it is not this year: "1 May 2020". */
function formatDate(iso: string, timeZone: string, now = new Date()): string {
  const { date, zone } = parse(iso, timeZone);
  return new Intl.DateTimeFormat(LOCALE, {
    month: 'short',
    day: 'numeric',
    ...year(date, zone, timeZone, now),
  }).format(date);
}

/** A date and time such as "13 Nov, 20:00", with the year when it is not this year. */
function formatDateTime(iso: string, timeZone: string, now = new Date()): string {
  const date = new Date(iso);
  return new Intl.DateTimeFormat(LOCALE, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
    ...year(date, timeZone, timeZone, now),
  }).format(date);
}

/** The time of an instant in a time zone, such as "20:00". */
function formatTime(instant: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, { timeStyle: 'short', timeZone }).format(new Date(instant));
}

/**
 * A coming day: its weekday until the end of the current week, which ends on Sunday ("Friday"), then its date
 * ("24 November"), with the year when it is another year's.
 */
function formatDay(day: string, today: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  const ahead = daysBetween(today, day);
  const toSunday = (7 - new Date(`${today}T00:00:00Z`).getUTCDay()) % 7;
  if (ahead >= 0 && ahead <= toSunday)
    return new Intl.DateTimeFormat(LOCALE, { weekday: 'long', timeZone: 'UTC' }).format(date);
  const other = day.slice(0, 4) !== today.slice(0, 4);
  return new Intl.DateTimeFormat(LOCALE, {
    month: 'long',
    day: 'numeric',
    year: other ? 'numeric' : undefined,
    timeZone: 'UTC',
  }).format(date);
}

/** A time zone with its current offset from GMT, such as "Europe/Paris (GMT+1)" or "UTC (GMT)". */
function zoneWithOffset(timeZone: string, now = new Date()): string {
  const offset = new Intl.DateTimeFormat(LOCALE, { timeZone, timeZoneName: 'shortOffset' })
    .formatToParts(now)
    .find((part) => part.type === 'timeZoneName')?.value;
  return offset ? `${timeZone} (${offset})` : timeZone;
}

/** The month of a day, such as "December", with another year's year: "January 2027". */
function formatMonth(day: string, today: string): string {
  const other = day.slice(0, 4) !== today.slice(0, 4);
  return new Intl.DateTimeFormat(LOCALE, {
    month: 'long',
    year: other ? 'numeric' : undefined,
    timeZone: 'UTC',
  }).format(new Date(`${day}T00:00:00Z`));
}

function year(date: Date, zone: string, timeZone: string, now: Date): Intl.DateTimeFormatOptions {
  return dayIn(zone, date).slice(0, 4) === dayIn(timeZone, now).slice(0, 4)
    ? { timeZone: zone }
    : { timeZone: zone, year: 'numeric' };
}
