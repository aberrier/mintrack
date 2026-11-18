export { dayIn, formatDay, formatTime, nextDay };

/** The calendar day (YYYY-MM-DD) of an instant in a time zone. */
function dayIn(timeZone: string, instant = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(
    instant,
  );
}

/** The day (YYYY-MM-DD) after a day. */
function nextDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

/** A day (YYYY-MM-DD) as a weekday and date: "Friday, November 20", or "Fri, Nov 20" when short. */
function formatDay(day: string, width: 'long' | 'short' = 'long'): string {
  return new Intl.DateTimeFormat(undefined, { weekday: width, month: width, day: 'numeric', timeZone: 'UTC' }).format(
    new Date(`${day}T00:00:00Z`),
  );
}

/** The time of an instant in a time zone, in the browser's locale. */
function formatTime(instant: string, timeZone: string): string {
  return new Intl.DateTimeFormat(undefined, { timeStyle: 'short', timeZone }).format(new Date(instant));
}
