import { unmatchedDetails } from './unmatched';

function item(changes: Partial<Model.Http.JellyfinUnmatchedItem>): Model.Http.JellyfinUnmatchedItem {
  return {
    name: 'Lost Film',
    type: 'Movie',
    year: 1990,
    provider_ids: { Imdb: 'tt404' },
    series_name: null,
    series_year: null,
    series_provider_ids: null,
    season: null,
    episode: null,
    reason: 'not_found',
    ...changes,
  };
}

describe('unmatchedDetails', () => {
  it('describes each item on one line, with its series and numbers for an episode', () => {
    const account = {
      last_sync_skipped: 5,
      last_sync_unmatched: [
        item({}),
        item({
          name: 'Episode 1',
          type: 'Episode',
          year: null,
          provider_ids: {},
          series_name: 'Nowhere Show',
          series_year: 2020,
          series_provider_ids: { Tvdb: '42' },
          season: 1,
          episode: 12,
          reason: 'episode_not_found',
        }),
        item({
          type: 'Episode',
          provider_ids: {},
          series_name: 'Gone',
          season: null,
          episode: 3,
          reason: 'no_numbers',
        }),
      ],
    } as Model.Http.JellyfinAccount;

    expect(unmatchedDetails(account).split('\n')).toEqual([
      'Jellyfin items not recognized: 5 (3 listed)',
      '- Movie · "Lost Film" (1990) · ids: Imdb=tt404 · not_found',
      '- Episode · "Episode 1" · S01E12 · ids: none · series "Nowhere Show" (2020), ids: Tvdb=42 · episode_not_found',
      '- Episode · "Lost Film" (1990) · S?E03 · ids: none · series "Gone", ids: series missing · no_numbers',
    ]);
  });
});
