import {
  episodeCode,
  followingEpisode,
  guessNext,
  isAired,
  isUpcoming,
  LoadedSeasons,
  previousUnwatched,
  seasonProgress,
} from './episodes';

const NOW = new Date('2026-06-10T12:00:00Z');
const UTC = 'UTC';

describe('episodeCode', () => {
  it('pads season and episode numbers', () => {
    expect(episodeCode(1, 5)).toBe('S01 | E05');
    expect(episodeCode(12, 104)).toBe('S12 | E104');
    expect(episodeCode(1, 5, true)).toBe('S01E05');
  });
});

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

/** Season 1 aired, season 2 aired but for its last episode, and one special. */
const EPISODES: LoadedSeasons = {
  1: [episode(1, 1, '2026-01-01'), episode(1, 2, '2026-01-08')],
  2: [episode(2, 1, '2026-06-01'), episode(2, 2, '2026-06-08'), episode(2, 3, '2026-06-15')],
  0: [episode(0, 1, '2026-02-01')],
};

function season(number: number, watched: number): Model.Http.Season {
  const episodes = EPISODES[number];
  return {
    season_number: number,
    title: `Season ${number}`,
    episode_count: episodes.length,
    watched_count: watched,
    aired_count: episodes.filter((other) => isAired(other, NOW, UTC)).length,
  };
}

function show(watched: string[]): Model.Http.Show {
  const count = (number: number) => watched.filter((id) => id.startsWith(`${number}x`)).length;
  return {
    tmdb_id: 1,
    title: 'Show',
    overview: '',
    poster_path: null,
    release_date: null,
    tmdb_status: 'Returning Series',
    backdrop_path: null,
    network: null,
    runtime: null,
    vote_average: null,
    vote_count: null,
    rating: null,
    seasons: [1, 2, 0].map((number) => season(number, count(number))),
    tracking: { status: 'watching', watched: Object.fromEntries(watched.map((id) => [id, '2026-06-01T00:00:00Z'])) },
    next_episode: null,
  };
}

/** Only the given seasons loaded. */
function only(...numbers: number[]): LoadedSeasons {
  return Object.fromEntries(numbers.map((number) => [number, EPISODES[number]]));
}

describe('previousUnwatched', () => {
  it('counts the earlier aired regular episodes not watched yet, across seasons', () => {
    const target = show(['1x1']);

    expect(previousUnwatched(target, EPISODES, EPISODES[2][1], NOW, UTC)).toBe(2);
  });

  it('counts a season not loaded by its counts', () => {
    const target = show(['1x1']);

    expect(previousUnwatched(target, only(2), EPISODES[2][1], NOW, UTC)).toBe(2);
  });

  it('never counts specials, nor anything for a special', () => {
    const target = show([]);

    expect(previousUnwatched(target, EPISODES, EPISODES[1][0], NOW, UTC)).toBe(0);
    expect(previousUnwatched(target, EPISODES, EPISODES[0][0], NOW, UTC)).toBe(0);
  });
});

describe('isUpcoming', () => {
  it('is true only for a known date after now, so an episode without a date can be marked', () => {
    expect(isUpcoming(episode(1, 1, '2026-06-11'), NOW, UTC)).toBe(true);
    expect(isUpcoming(episode(1, 1, '2026-06-10'), NOW, UTC)).toBe(false);
    expect(isUpcoming(episode(1, 1, null), NOW, UTC)).toBe(false);
  });
});

describe('isAired', () => {
  it('uses the exact air time when known, else the date', () => {
    expect(isAired(episode(1, 1, '2026-06-10'), NOW, UTC)).toBe(true);
    expect(isAired(episode(1, 1, '2026-06-11'), NOW, UTC)).toBe(false);
    expect(isAired({ ...episode(1, 1, '2026-06-10'), airstamp: '2026-06-10T23:00:00Z' }, NOW, UTC)).toBe(false);
    expect(isAired(episode(1, 1, null), NOW, UTC)).toBe(false);
  });

  it('starts the day in the user time zone, not the device one', () => {
    // Noon in UTC is already the next day in Auckland.
    expect(isAired(episode(1, 1, '2026-06-11'), NOW, 'Pacific/Auckland')).toBe(true);
    expect(isAired(episode(1, 1, '2026-06-11'), NOW, 'America/Los_Angeles')).toBe(false);
  });
});

describe('followingEpisode', () => {
  it('gives the next regular episode across seasons, with the aired unwatched ones after it', () => {
    const following = followingEpisode(show(['1x1', '1x2', '2x2']), EPISODES, 1, 2, NOW, UTC);

    expect(following?.id).toBe('2x1');
    // 2x2 is watched and 2x3 has not aired.
    expect(following?.remaining).toBe(0);
  });

  it('gives nothing after the last aired episode', () => {
    expect(followingEpisode(show([]), EPISODES, 2, 2, NOW, UTC)).toBeNull();
    expect(followingEpisode(show([]), EPISODES, 2, 3, NOW, UTC)).toBeNull();
  });

  it('cannot say when the season that holds it is not loaded', () => {
    expect(followingEpisode(show([]), only(1), 1, 2, NOW, UTC)).toBeUndefined();
    expect(followingEpisode(show([]), only(2), 1, 2, NOW, UTC)).toBeUndefined();
    expect(followingEpisode(show([]), only(1), 1, 1, NOW, UTC)?.id).toBe('1x2');
  });
});

describe('seasonProgress', () => {
  it('counts watched over aired from the season counts', () => {
    expect(seasonProgress(season(2, 1))).toEqual({ watched: 1, aired: 2, complete: false });
    expect(seasonProgress(season(1, 2))).toEqual({ watched: 2, aired: 2, complete: true });
  });

  it('counts an episode watched before its date as aired', () => {
    expect(seasonProgress({ ...season(2, 3) })).toEqual({ watched: 3, aired: 3, complete: true });
  });
});

describe('guessNext', () => {
  it('starts with the first regular episode', () => {
    expect(guessNext(show([]), EPISODES, NOW, UTC)).toMatchObject({ id: '1x1', remaining: 3 });
  });

  it('follows the latest episode watched, skipping gaps before it', () => {
    expect(guessNext(show(['1x1', '2x1']), EPISODES, NOW, UTC)?.id).toBe('2x2');
  });

  it('is nothing once the next one has not aired', () => {
    expect(guessNext(show(['2x2']), EPISODES, NOW, UTC)).toBeNull();
  });

  it('cannot say when a later season watched is not loaded', () => {
    expect(guessNext(show(['1x1', '2x1']), only(1), NOW, UTC)).toBeUndefined();
  });
});
