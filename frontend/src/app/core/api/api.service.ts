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
}
