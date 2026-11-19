import { dayIn } from '../dates';

export {
  earliestWatch,
  episodeCode,
  followingEpisode,
  guessNext,
  isAired,
  isUpcoming,
  isWatched,
  previousUnwatched,
  regularSeasonsBefore,
  seasonProgress,
  SPECIALS,
};

const SPECIALS = 0;

/** An episode's number as shown on cards: S01 | E05, or S01E05 where space is short. */
function episodeCode(season: number, episode: number, compact = false): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return compact ? `S${pad(season)}E${pad(episode)}` : `S${pad(season)} | E${pad(episode)}`;
}

/**
 * The earliest watch date the API takes for an episode: the start of the day before its air date in UTC, since that
 * day starts earlier in the zones ahead of UTC; 1 January 1900 UTC without an air date.
 */
function earliestWatch(airDate: string | null): Date {
  if (!airDate) return new Date(Date.UTC(1900, 0, 1));
  const day = new Date(`${airDate}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() - 1);
  return day;
}

/** A show's loaded episodes by season number; a season missing here was not loaded yet. */
export type LoadedSeasons = Readonly<Record<number, Model.Http.Episode[]>>;

export interface SeasonProgress {
  watched: number;
  /** Aired episodes, plus watched ones not aired as far as their date says. */
  aired: number;
  /** Every aired episode is watched. */
  complete: boolean;
}

/** Aired at its exact time when known, else on its date in the user's time zone. */
function isAired(episode: Model.Http.Episode, now: Date, timeZone: string): boolean {
  if (episode.airstamp) return new Date(episode.airstamp) <= now;
  return episode.air_date !== null && episode.air_date <= dayIn(timeZone, now);
}

/** Airs later, as far as its date says; an episode without a date is not upcoming, so it can be marked. */
function isUpcoming(episode: Model.Http.Episode, now: Date, timeZone: string): boolean {
  return (episode.airstamp !== null || episode.air_date !== null) && !isAired(episode, now, timeZone);
}

function isWatched(show: Pick<Model.Http.Show, 'tracking'>, episode: Pick<Model.Http.Episode, 'id'>): boolean {
  return !!show.tracking?.watched[episode.id];
}

/** The loaded episodes outside specials, in airing order. */
function regularEpisodes(loaded: LoadedSeasons): Model.Http.Episode[] {
  return Object.entries(loaded)
    .filter(([season]) => Number(season) !== SPECIALS)
    .flatMap(([, episodes]) => episodes)
    .sort((a, b) => a.season_number - b.season_number || a.episode_number - b.episode_number);
}

/** The regular seasons with episodes, in order. */
function regularSeasons(show: Model.Http.Show): Model.Http.Season[] {
  return show.seasons
    .filter((season) => season.season_number !== SPECIALS && season.episode_count > 0)
    .sort((a, b) => a.season_number - b.season_number);
}

/** The regular seasons before `season`, in order. */
function regularSeasonsBefore(show: Model.Http.Show, season: number): Model.Http.Season[] {
  return season === SPECIALS ? [] : regularSeasons(show).filter((other) => other.season_number < season);
}

function isBefore(a: Model.Http.Episode, b: Model.Http.Episode): boolean {
  return (
    a.season_number < b.season_number || (a.season_number === b.season_number && a.episode_number < b.episode_number)
  );
}

/**
 * How many aired regular episodes before `episode` are not watched, counted on the loaded seasons and, for the others,
 * on their counts. Marking them needs the earlier seasons loaded first.
 */
function previousUnwatched(
  show: Model.Http.Show,
  loaded: LoadedSeasons,
  episode: Model.Http.Episode,
  now: Date,
  timeZone: string,
): number {
  if (episode.season_number === SPECIALS) return 0;
  let count = 0;
  for (const season of [
    ...regularSeasonsBefore(show, episode.season_number),
    ...show.seasons.filter(({ season_number }) => season_number === episode.season_number),
  ]) {
    const episodes = loaded[season.season_number];
    if (!episodes) count += Math.max(0, season.aired_count - season.watched_count);
    else
      count += episodes.filter(
        (other) => isBefore(other, episode) && isAired(other, now, timeZone) && !isWatched(show, other),
      ).length;
  }
  return count;
}

/**
 * The regular episode after `season`x`episode` once it is watched, if it aired (an undated one counts as aired when a
 * later one of its season has), with the number of aired, unwatched episodes after it. null when there is none,
 * undefined when the seasons that would say are not loaded.
 */
function followingEpisode(
  show: Model.Http.Show,
  loaded: LoadedSeasons,
  season: number,
  episode: number,
  now: Date,
  timeZone: string,
): Model.Http.NextEpisode | null | undefined {
  const regular = regularEpisodes(loaded);
  const index = regular.findIndex(
    (candidate) =>
      candidate.season_number > season || (candidate.season_number === season && candidate.episode_number > episode),
  );
  const next: Model.Http.Episode | undefined = regular[index];
  const later = regularSeasons(show).filter((other) => other.season_number >= season);
  const unknown = later.some(
    (other) => !loaded[other.season_number] && (!next || other.season_number < next.season_number),
  );
  if (unknown) return undefined;
  if (!next) return null;
  const after = regular.slice(index + 1);
  const aired = (other: Model.Http.Episode) => isAired(other, now, timeZone);
  const undated = next.air_date === null && next.airstamp === null;
  if (!aired(next) && !(undated && after.some((other) => other.season_number === next.season_number && aired(other))))
    return null;
  const notLoaded = later
    .filter((other) => !loaded[other.season_number])
    .reduce((sum, other) => sum + Math.max(0, other.aired_count - other.watched_count), 0);
  return {
    ...next,
    remaining: after.filter((other) => aired(other) && !isWatched(show, other)).length + notLoaded,
  };
}

/** A season row's `watched/aired` from its counts, which the store keeps in step with the marks. */
function seasonProgress(season: Model.Http.Season): SeasonProgress {
  const watched = season.watched_count;
  const aired = Math.max(season.aired_count, watched);
  return { watched, aired, complete: aired > 0 && watched >= aired };
}

/**
 * The episode to watch next as the screen shows it right after a tap, until the server's answer: the regular episode
 * after the latest one watched, or the first one when none is. undefined when the loaded seasons cannot say.
 */
function guessNext(
  show: Model.Http.Show,
  loaded: LoadedSeasons,
  now: Date,
  timeZone: string,
): Model.Http.NextEpisode | null | undefined {
  const latest = regularEpisodes(loaded)
    .filter((episode) => isWatched(show, episode))
    .at(-1);
  const watchedElsewhere = regularSeasons(show).some(
    (season) =>
      !loaded[season.season_number] &&
      season.watched_count > 0 &&
      (!latest || season.season_number > latest.season_number),
  );
  if (watchedElsewhere) return undefined;
  return latest
    ? followingEpisode(show, loaded, latest.season_number, latest.episode_number, now, timeZone)
    : followingEpisode(show, loaded, SPECIALS, Number.MAX_SAFE_INTEGER, now, timeZone);
}
