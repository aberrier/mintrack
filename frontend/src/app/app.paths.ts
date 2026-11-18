/** Every in-app URL, built here so links and routes cannot drift apart. */
export const appRoutes = {
  home: (rp = '/') => `${rp}`,
  login: (next?: string, rp = '/') => `${rp}login${next ? `?next=${encodeURIComponent(next)}` : ''}`,
  password: (rp = '/') => `${rp}password`,
  profile: (rp = '/') => `${rp}profile`,
  adminUsers: (rp = '/') => `${rp}admin/users`,
};
