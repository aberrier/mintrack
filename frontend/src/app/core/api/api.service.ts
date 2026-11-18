import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

/**
 * The MinTrack API, one group of endpoints per domain.
 * URLs are relative: the backend serves this app, so the API is always on the same origin.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  readonly health = {
    get: () => this.http.get<Model.Http.HealthResponse>('/api/health'),
  };

  readonly auth = {
    login: (username: string, password: string) =>
      this.http.post<Model.Http.User>('/api/auth/login', { username, password }),
    me: () => this.http.get<Model.Http.User>('/api/auth/me'),
    updateMe: (timezone: string) => this.http.patch<Model.Http.User>('/api/auth/me', { timezone }),
    logout: () => this.http.post<void>('/api/auth/logout', null),
    logoutEverywhere: () => this.http.post<void>('/api/auth/logout-all', null),
    changePassword: (currentPassword: string, newPassword: string) =>
      this.http.post<void>('/api/auth/password', { current_password: currentPassword, new_password: newPassword }),
    describeLink: (token: string) => this.http.post<Model.Http.PasswordLink>('/api/auth/password-link', { token }),
    /** The time zone is only stored for a user who never had a password. */
    useLink: (token: string, password: string, timezone: string) =>
      this.http.post<Model.Http.User>('/api/auth/password-link/use', { token, password, timezone }),
  };

  readonly adminUsers = {
    list: () => this.http.get<Model.Http.AdminUser[]>('/api/admin/users'),
    create: (username: string) => this.http.post<Model.Http.CreatedUser>('/api/admin/users', { username }),
    newLink: (id: string) => this.http.post<Model.Http.Link>(`/api/admin/users/${id}/link`, null),
    setActive: (id: string, isActive: boolean) =>
      this.http.patch<Model.Http.AdminUser>(`/api/admin/users/${id}`, { is_active: isActive }),
  };

  readonly catalog = {
    search: (query: string) => this.http.get<Model.Http.SearchResult[]>('/api/search', { params: { query } }),
    show: (tmdbId: number) => this.http.get<Model.Http.Show>(`/api/shows/${tmdbId}`),
    movie: (tmdbId: number) => this.http.get<Model.Http.Movie>(`/api/movies/${tmdbId}`),
  };

  readonly tracking = {
    trackShow: (tmdbId: number, stopped: boolean) =>
      this.http.put<Model.Http.ShowTracking>(`/api/shows/${tmdbId}/tracking`, { stopped }),
    untrackShow: (tmdbId: number) => this.http.delete<void>(`/api/shows/${tmdbId}/tracking`),
    setWatched: (tmdbId: number, episodeIds: string[], watched: boolean) =>
      this.http.post<Model.Http.ShowTracking | null>(`/api/shows/${tmdbId}/watched`, {
        episode_ids: episodeIds,
        watched,
      }),
    trackMovie: (tmdbId: number, watched: boolean) =>
      this.http.put<Model.Http.MovieTracking>(`/api/movies/${tmdbId}/tracking`, { watched }),
    untrackMovie: (tmdbId: number) => this.http.delete<void>(`/api/movies/${tmdbId}/tracking`),
    library: (mediaType: Model.Http.MediaType) =>
      this.http.get<Model.Http.LibraryItem[]>('/api/library', { params: { media_type: mediaType } }),
  };

  readonly upcoming = {
    get: () => this.http.get<Model.Http.UpcomingResponse>('/api/upcoming'),
    upNext: () => this.http.get<Model.Http.UpNextResponse>('/api/up-next'),
  };

  readonly push = {
    key: () => this.http.get<Model.Http.PushKeyResponse>('/api/push/key'),
    subscribe: (subscription: PushSubscriptionJSON) => this.http.post<void>('/api/push/subscriptions', subscription),
    unsubscribe: (endpoint: string) => this.http.delete<void>('/api/push/subscriptions', { body: { endpoint } }),
    test: (endpoint: string) => this.http.post<void>('/api/push/test', { endpoint }),
  };
}
