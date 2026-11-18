import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { computed, inject, Injectable, InjectionToken, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../api/api.service';

/** Where the app reloads from scratch; replaced in tests. */
export const PAGE_LOCATION = new InjectionToken<Pick<Location, 'assign'>>('PAGE_LOCATION', {
  providedIn: 'root',
  factory: () => inject(DOCUMENT).location,
});

/** unreachable: offline, or nothing answers for the server (a proxy's 502 to 504); error: the server failed. */
export type AuthFailure = 'unreachable' | 'error';

const UNREACHABLE_STATUSES = [0, 502, 503, 504];

/** The signed-in user: `undefined` until the server was asked, `null` when signed out. */
@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly api = inject(ApiService);
  private readonly location = inject(PAGE_LOCATION);
  private readonly user = signal<Model.Http.User | null | undefined>(undefined);
  private readonly failure = signal<AuthFailure | null>(null);
  private loading?: Promise<Model.Http.User | null>;

  readonly $user = this.user.asReadonly();
  readonly $isAdmin = computed(() => this.user()?.is_admin ?? false);
  /** The user's time zone, in which days start and air times show; the device's until signed in. */
  readonly $timeZone = computed(() => this.user()?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone);
  /** Why the server could not say who is signed in, if it could not. */
  readonly $failure = this.failure.asReadonly();
  /** The page that could not open meanwhile, to open on Try again. */
  blockedUrl: string | null = null;

  /** The current user, asking the server only the first time. */
  load(): Promise<Model.Http.User | null> {
    const user = this.user();
    if (user !== undefined) return Promise.resolve(user);
    this.loading ??= firstValueFrom(this.api.auth.me())
      .catch((error: unknown) => {
        if (error instanceof HttpErrorResponse && error.status === 401) return null;
        const status = error instanceof HttpErrorResponse ? error.status : 0;
        this.failure.set(UNREACHABLE_STATUSES.includes(status) ? 'unreachable' : 'error');
        throw error;
      })
      .then((me) => {
        this.failure.set(null);
        this.blockedUrl = null;
        this.user.set(me);
        return me;
      })
      .finally(() => (this.loading = undefined));
    return this.loading;
  }

  set(user: Model.Http.User): void {
    this.user.set(user);
  }

  clear(): void {
    this.user.set(null);
  }

  /** Start the app afresh at `url`: nothing loaded for the previous user stays in memory. */
  restartAt(url: string): void {
    this.location.assign(url);
  }

  async login(username: string, password: string): Promise<void> {
    this.user.set(await firstValueFrom(this.api.auth.login(username, password)));
  }

  /** Signed out locally even when the server already ended the session. */
  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.api.auth.logout());
    } finally {
      this.clear();
    }
  }

  async logoutEverywhere(): Promise<void> {
    try {
      await firstValueFrom(this.api.auth.logoutEverywhere());
    } finally {
      this.clear();
    }
  }
}
