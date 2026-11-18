/** Every in-app URL, built here so links and routes cannot drift apart. */
export const appRoutes = {
  home: (rp = '/') => `${rp}`,
  upNext: (rp = '/') => `${rp}up-next`,
  upcoming: (rp = '/') => `${rp}upcoming`,
  login: (next?: string, rp = '/') => `${rp}login${next ? `?next=${encodeURIComponent(next)}` : ''}`,
  password: (rp = '/') => `${rp}password`,
  profile: (rp = '/') => `${rp}profile`,
  adminUsers: (rp = '/') => `${rp}admin/users`,
  library: (rp = '/') => `${rp}library`,
  search: (rp = '/') => `${rp}search`,
  show: (tmdbId: number | string, rp = '/') => `${rp}shows/${tmdbId}`,
  movie: (tmdbId: number | string, rp = '/') => `${rp}movies/${tmdbId}`,
};
