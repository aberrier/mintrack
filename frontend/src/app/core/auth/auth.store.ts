import { HttpErrorResponse } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../api/api.service';

/** The signed-in user: `undefined` until the server was asked, `null` when signed out. */
@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly api = inject(ApiService);
  private readonly user = signal<Model.Http.User | null | undefined>(undefined);
  private loading?: Promise<Model.Http.User | null>;

  readonly $user = this.user.asReadonly();
  readonly $isAdmin = computed(() => this.user()?.is_admin ?? false);

  /** The current user, asking the server only the first time. */
  load(): Promise<Model.Http.User | null> {
    const user = this.user();
    if (user !== undefined) return Promise.resolve(user);
    this.loading ??= firstValueFrom(this.api.auth.me())
      .catch((error: unknown) => {
        if (error instanceof HttpErrorResponse && error.status === 401) return null;
        throw error;
      })
      .then((me) => {
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
