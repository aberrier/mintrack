/**
 * A plain text block describing the items an account's last full sync did not recognize, one line each, to paste in a
 * bug report: what Jellyfin says of each item and why MinTrack found no match.
 */
export function unmatchedDetails(account: Model.Http.JellyfinAccount): string {
  const items = account.last_sync_unmatched;
  const header = `Jellyfin items not recognized: ${account.last_sync_skipped} (${items.length} listed)`;
  return [header, ...items.map((item) => `- ${unmatchedLine(item)}`)].join('\n');
}

function unmatchedLine(item: Model.Http.JellyfinUnmatchedItem): string {
  const parts = [item.type, titled(item.name, item.year)];
  if (item.season !== null || item.episode !== null) parts.push(`S${number(item.season)}E${number(item.episode)}`);
  parts.push(`ids: ${ids(item.provider_ids)}`);
  if (item.series_name !== null || item.series_provider_ids !== null) {
    const series = titled(item.series_name ?? '', item.series_year);
    parts.push(`series ${series}, ids: ${item.series_provider_ids ? ids(item.series_provider_ids) : 'series missing'}`);
  }
  parts.push(item.reason);
  return parts.join(' · ');
}

function titled(name: string, year: number | null): string {
  return year === null ? `"${name}"` : `"${name}" (${year})`;
}

function number(value: number | null): string {
  return value === null ? '?' : String(value).padStart(2, '0');
}

function ids(providerIds: Record<string, string>): string {
  const entries = Object.entries(providerIds);
  return entries.length ? entries.map(([provider, id]) => `${provider}=${id}`).join(', ') : 'none';
}
