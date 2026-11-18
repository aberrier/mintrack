export {
  ENDED_STATUSES,
  SPECIALS,
  backdropUrl,
  episodeCode,
  followingEpisode,
  isAired,
  isComplete,
  isUpcoming,
  isWatched,
  nextToWatch,
  posterUrl,
  previousUnwatched,
  seasonProgress,
};

const SPECIALS = 0;
/** TMDB statuses of a show that will air nothing more. */
const ENDED_STATUSES: readonly (string | null)[] = ['Ended', 'Canceled'];

export interface SeasonProgress {
  watched: number;
  /** Aired episodes, plus watched ones not aired as far as their date says. */
  aired: number;
  /** Aired, dated episodes not watched yet: what one tap on the season marks. */
  toMark: Model.Http.Episode[];
  /** Every aired episode is watched. */
  complete: boolean;
}

/** Aired at its exact time when known, else on its date in the device's time zone. */
function isAired(episode: Model.Http.Episode, now: Date): boolean {
  if (episode.airstamp) return new Date(episode.airstamp) <= now;
  return episode.air_date !== null && episode.air_date <= localDate(now);
}

/** Airs later, as far as its date says; an episode without a date is not upcoming, so it can be marked. */
function isUpcoming(episode: Model.Http.Episode, now: Date): boolean {
  return (episode.airstamp !== null || episode.air_date !== null) && !isAired(episode, now);
}

function isWatched(show: Model.Http.Show, episode: Model.Http.Episode): boolean {
  return !!show.tracking?.watched[episode.id];
}

/** The aired regular episodes before `episode` that are not watched, in airing order. */
function previousUnwatched(show: Model.Http.Show, episode: Model.Http.Episode, now: Date): Model.Http.Episode[] {
  if (episode.season_number === SPECIALS) return [];
  return show.seasons
    .filter((season) => season.season_number !== SPECIALS)
    .flatMap((season) => season.episodes)
    .filter(
      (candidate) =>
        (candidate.season_number < episode.season_number ||
          (candidate.season_number === episode.season_number && candidate.episode_number < episode.episode_number)) &&
        isAired(candidate, now) &&
        !isWatched(show, candidate),
    );
}

/**
 * The regular episode after `season`x`episode` once it is watched, if it aired (an undated one counts as aired when a
 * later one of its season has), with the number of aired, unwatched episodes after it.
 */
function followingEpisode(
  show: Model.Http.Show,
  season: number,
  episode: number,
  now: Date,
): { episode: Model.Http.Episode; remaining: number } | null {
  const regular = show.seasons
    .filter((candidate) => candidate.season_number !== SPECIALS)
    .flatMap((candidate) => candidate.episodes)
    .sort((a, b) => a.season_number - b.season_number || a.episode_number - b.episode_number);
  const index = regular.findIndex(
    (candidate) =>
      candidate.season_number > season || (candidate.season_number === season && candidate.episode_number > episode),
  );
  if (index === -1) return null;
  const next = regular[index];
  const later = regular.slice(index + 1);
  const undated = next.air_date === null && next.airstamp === null;
  const aired =
    isAired(next, now) ||
    (undated && later.some((other) => other.season_number === next.season_number && isAired(other, now)));
  if (!aired) return null;
  return { episode: next, remaining: later.filter((other) => isAired(other, now) && !isWatched(show, other)).length };
}

function seasonProgress(show: Model.Http.Show, season: Model.Http.Season, now: Date): SeasonProgress {
  let watched = 0;
  let aired = 0;
  const toMark: Model.Http.Episode[] = [];
  for (const episode of season.episodes) {
    const seen = isWatched(show, episode);
    const out = isAired(episode, now);
    if (seen) watched++;
    if (seen || out) aired++;
    if (out && !seen) toMark.push(episode);
  }
  return { watched, aired, toMark, complete: aired > 0 && toMark.length === 0 };
}

/**
 * The episode to watch next: the regular episode after the latest one watched, or the first one when none is, as long
 * as it aired, with the number of aired, unwatched episodes after it.
 */
function nextToWatch(show: Model.Http.Show, now: Date): { episode: Model.Http.Episode; remaining: number } | null {
  let latest: Model.Http.Episode | null = null;
  for (const season of show.seasons) {
    if (season.season_number === SPECIALS) continue;
    for (const episode of season.episodes) {
      if (
        isWatched(show, episode) &&
        (!latest ||
          episode.season_number > latest.season_number ||
          (episode.season_number === latest.season_number && episode.episode_number > latest.episode_number))
      )
        latest = episode;
    }
  }
  return latest
    ? followingEpisode(show, latest.season_number, latest.episode_number, now)
    : followingEpisode(show, SPECIALS, Number.MAX_SAFE_INTEGER, now);
}

/**
 * An ended show whose dated regular episodes are all watched, as the server decides it is finished; an episode without
 * a date is neither aired nor upcoming.
 */
function isComplete(show: Model.Http.Show, now: Date): boolean {
  if (!ENDED_STATUSES.includes(show.tmdb_status)) return false;
  const episodes = show.seasons
    .filter((season) => season.season_number !== SPECIALS)
    .flatMap((season) => season.episodes);
  return (
    episodes.some((episode) => isWatched(show, episode)) &&
    episodes.every((episode) => isWatched(show, episode) || (!isAired(episode, now) && !isUpcoming(episode, now)))
  );
}

/** An episode's number as shown on cards: S01 | E05. */
function episodeCode(season: number, episode: number): string {
  return `S${pad(season)} | E${pad(episode)}`;
}

function posterUrl(path: string | null, width: 'w185' | 'w342' = 'w185'): string | null {
  return path ? `https://image.tmdb.org/t/p/${width}${path}` : null;
}

function backdropUrl(path: string | null): string | null {
  return path ? `https://image.tmdb.org/t/p/w780${path}` : null;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

function localDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
