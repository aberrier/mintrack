import { isAired, isUpcoming, previousUnwatched } from './episodes';

const NOW = new Date(2026, 5, 10, 12);

function episode(season: number, number: number, airDate: string | null): Model.Http.Episode {
  return {
    id: `${season}x${number}`,
    season_number: season,
    episode_number: number,
    title: '',
    air_date: airDate,
    airstamp: null,
  };
}

function show(watched: string[]): Model.Http.Show {
  const seasons = [
    [episode(1, 1, '2026-01-01'), episode(1, 2, '2026-01-08')],
    [episode(2, 1, '2026-06-01'), episode(2, 2, '2026-06-08'), episode(2, 3, '2026-06-15')],
    [episode(0, 1, '2026-02-01')],
  ];
  return {
    tmdb_id: 1,
    title: 'Show',
    overview: '',
    poster_path: null,
    release_date: null,
    tmdb_status: 'Returning Series',
    seasons: seasons.map((episodes) => ({
      season_number: episodes[0].season_number,
      title: '',
      episodes,
    })),
    tracking: { status: 'watching', watched: Object.fromEntries(watched.map((id) => [id, '2026-06-01T00:00:00Z'])) },
  };
}

describe('previousUnwatched', () => {
  it('lists the earlier aired regular episodes not watched yet, across seasons', () => {
    const target = show(['1x1']);

    const previous = previousUnwatched(target, target.seasons[1].episodes[1], NOW);

    expect(previous.map((e) => e.id)).toEqual(['1x2', '2x1']);
  });

  it('never offers specials, nor anything for a special', () => {
    const target = show([]);

    expect(previousUnwatched(target, target.seasons[0].episodes[0], NOW)).toEqual([]);
    expect(previousUnwatched(target, target.seasons[2].episodes[0], NOW)).toEqual([]);
  });
});

describe('isUpcoming', () => {
  it('is true only for a known date after now, so an episode without a date can be marked', () => {
    expect(isUpcoming(episode(1, 1, '2026-06-11'), NOW)).toBe(true);
    expect(isUpcoming(episode(1, 1, '2026-06-10'), NOW)).toBe(false);
    expect(isUpcoming(episode(1, 1, null), NOW)).toBe(false);
  });
});

describe('isAired', () => {
  it('uses the exact air time when known, else the date', () => {
    expect(isAired(episode(1, 1, '2026-06-10'), NOW)).toBe(true);
    expect(isAired(episode(1, 1, '2026-06-11'), NOW)).toBe(false);
    expect(isAired({ ...episode(1, 1, '2026-06-10'), airstamp: '2026-06-10T23:00:00Z' }, NOW)).toBe(false);
    expect(isAired(episode(1, 1, null), NOW)).toBe(false);
  });
});
