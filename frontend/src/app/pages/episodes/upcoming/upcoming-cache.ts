import { Injectable, signal } from '@angular/core';

/** The last list loaded, shown at once when their page comes back, so it keeps its scroll position. */
@Injectable({ providedIn: 'root' })
export class UpcomingCache {
  readonly upcoming = signal<Model.Http.UpcomingResponse | undefined>(undefined);
}
