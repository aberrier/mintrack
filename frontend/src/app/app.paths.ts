/** Every in-app URL, built here so links and routes cannot drift apart. */
export const appRoutes = {
  episodes: (rp = '/') => `${rp}episodes`,
  watchList: (rp = '/') => `${rp}episodes/watch-list`,
  upcoming: (rp = '/') => `${rp}episodes/upcoming`,
  discover: (rp = '/') => `${rp}discover`,
  login: (next?: string, rp = '/') => `${rp}login${next ? `?next=${encodeURIComponent(next)}` : ''}`,
  password: (rp = '/') => `${rp}password`,
  profile: (rp = '/') => `${rp}profile`,
  collection: (rp = '/') => `${rp}profile/collection`,
  settings: (rp = '/') => `${rp}profile/settings`,
  mcpHelp: (rp = '/') => `${rp}profile/settings/mcp`,
  admin: (rp = '/') => `${rp}admin`,
  show: (tmdbId: number | string, rp = '/') => `${rp}shows/${tmdbId}`,
  movie: (tmdbId: number | string, rp = '/') => `${rp}movies/${tmdbId}`,
  /** A show's or a movie's page. */
  media: (mediaType: 'tv' | 'movie', tmdbId: number) =>
    mediaType === 'tv' ? appRoutes.show(tmdbId) : appRoutes.movie(tmdbId),
};
