import {
  episodeCode,
  followingEpisode,
  isAired,
  isComplete,
  isUpcoming,
  nextToWatch,
  previousUnwatched,
  seasonProgress,
} from './episodes';

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
    backdrop_path: null,
    network: null,
    runtime: null,
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

describe('followingEpisode', () => {
  it('gives the next regular episode across seasons, with the aired unwatched ones after it', () => {
    const target = show(['1x1', '1x2', '2x2']);

    const following = followingEpisode(target, 1, 2, NOW);

    expect(following?.episode.id).toBe('2x1');
    // 2x2 is watched and 2x3 has not aired.
    expect(following?.remaining).toBe(0);
  });

  it('gives nothing after the last aired episode', () => {
    expect(followingEpisode(show([]), 2, 2, NOW)).toBeNull();
    expect(followingEpisode(show([]), 2, 3, NOW)).toBeNull();
  });
});

describe('episodeCode', () => {
  it('pads season and episode numbers', () => {
    expect(episodeCode(1, 5)).toBe('S01 | E05');
    expect(episodeCode(12, 104)).toBe('S12 | E104');
  });
});

describe('seasonProgress', () => {
  it('counts watched over aired and lists the aired episodes left to mark, never the unaired one', () => {
    const target = show(['2x1']);

    const progress = seasonProgress(target, target.seasons[1], NOW);

    expect(progress).toMatchObject({ watched: 1, aired: 2, complete: false });
    expect(progress.toMark.map((e) => e.id)).toEqual(['2x2']);
  });

  it('is complete once every aired episode is watched', () => {
    const target = show(['1x1', '1x2']);

    expect(seasonProgress(target, target.seasons[0], NOW)).toMatchObject({ watched: 2, aired: 2, complete: true });
  });
});

describe('nextToWatch', () => {
  it('starts with the first regular episode', () => {
    const next = nextToWatch(show([]), NOW);

    expect(next?.episode.id).toBe('1x1');
    expect(next?.remaining).toBe(3);
  });

  it('follows the latest episode watched, skipping gaps before it', () => {
    expect(nextToWatch(show(['1x1', '2x1']), NOW)?.episode.id).toBe('2x2');
  });

  it('is nothing once the next one has not aired', () => {
    expect(nextToWatch(show(['2x2']), NOW)).toBeNull();
  });
});

describe('isComplete', () => {
  const ended = (watched: string[]) => ({ ...show(watched), tmdb_status: 'Ended' });

  it('is true for an ended show whose dated regular episodes are all watched, specials aside', () => {
    expect(isComplete(ended(['1x1', '1x2', '2x1', '2x2', '2x3']), NOW)).toBe(true);

    const undatedLast = ended(['1x1', '1x2', '2x1', '2x2']);
    undatedLast.seasons[1].episodes[2] = episode(2, 3, null);
    expect(isComplete(undatedLast, NOW)).toBe(true);
  });

  it('is false while an episode is still to air, or for a show still running', () => {
    expect(isComplete(ended(['1x1', '1x2', '2x1', '2x2']), NOW)).toBe(false);
    expect(isComplete(show(['1x1', '1x2', '2x1', '2x2', '2x3']), NOW)).toBe(false);
  });
});
