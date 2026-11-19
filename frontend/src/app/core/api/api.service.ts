import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

/**
 * The MinTrack API, one group of endpoints per domain.
 * URLs are relative: the backend serves this app, so the API is always on the same origin.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  readonly auth = {
    login: (username: string, password: string) =>
      this.http.post<Model.Http.User>('/api/auth/login', { username, password }),
    me: () => this.http.get<Model.Http.User>('/api/auth/me'),
    setupState: () => this.http.get<Model.Http.SetupState>('/api/auth/setup'),
    setUp: (username: string, password: string, timezone: string) =>
      this.http.post<Model.Http.User>('/api/auth/setup', { username, password, timezone }),
    updateMe: (timezone: string) => this.http.patch<Model.Http.User>('/api/auth/me', { timezone }),
    timezones: () => this.http.get<Model.Http.Timezone[]>('/api/auth/timezones'),
    logout: () => this.http.post<void>('/api/auth/logout', null),
    logoutEverywhere: () => this.http.post<void>('/api/auth/logout-all', null),
    sessions: () => this.http.get<Model.Http.Session[]>('/api/auth/sessions'),
    deleteSession: (id: string) => this.http.delete<void>(`/api/auth/sessions/${id}`),
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
    search: (query: string, type: Model.Http.MediaType) =>
      this.http.get<Model.Http.SearchResult[]>('/api/search', { params: { query, type } }),
    show: (tmdbId: number) => this.http.get<Model.Http.Show>(`/api/shows/${tmdbId}`),
    season: (tmdbId: number, seasonNumber: number) =>
      this.http.get<Model.Http.SeasonEpisodes>(`/api/shows/${tmdbId}/seasons/${seasonNumber}`),
    movie: (tmdbId: number) => this.http.get<Model.Http.Movie>(`/api/movies/${tmdbId}`),
    trending: (type: Model.Http.MediaType) =>
      this.http.get<Model.Http.SearchResult[]>('/api/discover/trending', { params: { type } }),
  };

  readonly tracking = {
    trackShow: (tmdbId: number, status: Model.Http.ShowTrackingChoice) =>
      this.http.put<Model.Http.ShowTracking>(`/api/shows/${tmdbId}/tracking`, { status }),
    untrackShow: (tmdbId: number) => this.http.delete<void>(`/api/shows/${tmdbId}/tracking`),
    setWatched: (tmdbId: number, episodeIds: string[], watched: boolean) =>
      this.http.post<Model.Http.ShowTracking | null>(`/api/shows/${tmdbId}/watched`, {
        episode_ids: episodeIds,
        watched,
      }),
    trackMovie: (tmdbId: number, watched: boolean) =>
      this.http.put<Model.Http.MovieTracking>(`/api/movies/${tmdbId}/tracking`, { watched }),
    untrackMovie: (tmdbId: number) => this.http.delete<void>(`/api/movies/${tmdbId}/tracking`),
    library: ({
      mediaType,
      sort = 'last_watched',
      status = null,
    }: {
      mediaType: Model.Http.MediaType;
      sort?: Model.Http.LibrarySort;
      status?: Model.Http.TrackingStatus | null;
    }) =>
      this.http.get<Model.Http.LibraryItem[]>('/api/library', {
        params: { media_type: mediaType, sort, ...(status ? { status } : {}) },
      }),
    /** A page of the watch history, newest first, before the given entry when there is one. */
    history: (before?: Pick<Model.Http.HistoryEntry, 'watched_at' | 'id'>) =>
      this.http.get<Model.Http.HistoryResponse>('/api/history', {
        params: before ? { before: before.watched_at, before_id: before.id } : {},
      }),
  };

  readonly upcoming = {
    get: () => this.http.get<Model.Http.UpcomingResponse>('/api/upcoming'),
    watchList: () => this.http.get<Model.Http.WatchListResponse>('/api/watch-list'),
  };

  readonly push = {
    key: () => this.http.get<Model.Http.PushKeyResponse>('/api/push/key'),
    subscribe: (subscription: PushSubscriptionJSON) => this.http.post<void>('/api/push/subscriptions', subscription),
    unsubscribe: (endpoint: string) => this.http.delete<void>('/api/push/subscriptions', { body: { endpoint } }),
    test: (endpoint: string) => this.http.post<void>('/api/push/test', { endpoint }),
  };

  readonly jellyfin = {
    list: () => this.http.get<Model.Http.JellyfinAccount[]>('/api/jellyfin/accounts'),
    link: (request: Model.Http.JellyfinLinkRequest) =>
      this.http.post<Model.Http.JellyfinAccount>('/api/jellyfin/accounts', request),
    /** Start a Quick Connect request: its code is approved in a Jellyfin app, its secret polls and links. */
    startQuickConnect: (request: Model.Http.JellyfinServerRequest) =>
      this.http.post<Model.Http.QuickConnect>('/api/jellyfin/quick-connect', request),
    quickConnectState: (request: Model.Http.QuickConnectRequest) =>
      this.http.post<Model.Http.QuickConnectState>('/api/jellyfin/quick-connect/state', request),
    linkQuickConnect: (request: Model.Http.QuickConnectRequest) =>
      this.http.post<Model.Http.JellyfinAccount>('/api/jellyfin/accounts/quick-connect', request),
    unlink: (id: string) => this.http.delete<void>(`/api/jellyfin/accounts/${id}`),
    sync: (id: string) => this.http.post<void>(`/api/jellyfin/accounts/${id}/sync`, null),
  };

  readonly imports = {
    latest: () => this.http.get<Model.Http.ImportJob | null>('/api/imports/latest'),
    create: (source: Model.Http.ImportSource, file: File) => {
      const body = new FormData();
      body.append('source', source);
      body.append('file', file);
      return this.http.post<Model.Http.ImportJob>('/api/imports', body);
    },
  };

  readonly apiTokens = {
    list: () => this.http.get<Model.Http.ApiToken[]>('/api/api-tokens'),
    create: (name: string) => this.http.post<Model.Http.CreatedApiToken>('/api/api-tokens', { name }),
    revoke: (id: string) => this.http.delete<void>(`/api/api-tokens/${id}`),
  };

  readonly about = () => this.http.get<Model.Http.About>('/api/about');
}
