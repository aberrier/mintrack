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
}
