export { SPECIALS, isAired, isUpcoming, isWatched, posterUrl, previousUnwatched };

const SPECIALS = 0;

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

function posterUrl(path: string | null, width: 'w185' | 'w342' = 'w185'): string | null {
  return path ? `https://image.tmdb.org/t/p/${width}${path}` : null;
}

function localDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
