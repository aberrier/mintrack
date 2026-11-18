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
  adminUsers: (rp = '/') => `${rp}admin/users`,
  show: (tmdbId: number | string, rp = '/') => `${rp}shows/${tmdbId}`,
  movie: (tmdbId: number | string, rp = '/') => `${rp}movies/${tmdbId}`,
};

/** Paths of earlier versions, still bookmarked, and where each one now lives. */
export const legacyRedirects: Record<string, string> = {
  'up-next': appRoutes.watchList(),
  upcoming: appRoutes.upcoming(),
  library: appRoutes.collection(),
  search: appRoutes.discover(),
};
