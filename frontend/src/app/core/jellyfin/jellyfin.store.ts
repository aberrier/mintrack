import { DestroyRef, inject, Injectable, signal } from '@angular/core';
import { Observable, Subscription, switchMap, take, takeWhile, tap, timer } from 'rxjs';
import { ApiService } from '../api/api.service';
import { injectTranslator, TranslationPath } from '../i18n';
import { injectNotify } from '../notify';

/** Milliseconds between two looks at an account whose sync was asked for. */
export const SYNC_POLL_MS = 3000;
const SYNC_POLL_COUNT = 40;

/** The signed-in user's linked Jellyfin accounts. */
@Injectable({ providedIn: 'root' })
export class JellyfinStore {
  private readonly api = inject(ApiService);
  private readonly showMessage = injectNotify();
  private readonly translate = injectTranslator('app');

  private readonly accounts = signal<Model.Http.JellyfinAccount[] | undefined>(undefined);
  /** Accounts whose sync is being followed, by id. */
  private readonly following = new Map<string, Subscription>();

  constructor() {
    inject(DestroyRef).onDestroy(() => this.following.forEach((subscription) => subscription.unsubscribe()));
  }
  readonly $accounts = this.accounts.asReadonly();

  load(): void {
    this.api.jellyfin.list().subscribe({
      next: (accounts) => this.accounts.set(accounts),
      error: () => this.notify('app.profile.jellyfin.loadFailed'),
    });
  }

  /** Link with a username and password; errors are left to the caller, which shows them next to the form. */
  link(request: Model.Http.JellyfinLinkRequest): Observable<Model.Http.JellyfinAccount> {
    return this.api.jellyfin.link(request).pipe(tap((linked) => this.add(linked)));
  }

  /** Link the account that approved a Quick Connect request; errors are left to the caller. */
  linkQuickConnect(request: Model.Http.QuickConnectRequest): Observable<Model.Http.JellyfinAccount> {
    return this.api.jellyfin.linkQuickConnect(request).pipe(tap((linked) => this.add(linked)));
  }

  /**
   * Ask for the accounts again every few seconds until the account's sync has run, for at most two minutes, so its line
   * shows how the sync went without a reload.
   */
  private followSync(account: Model.Http.JellyfinAccount): void {
    this.following.get(account.id)?.unsubscribe();
    this.following.set(
      account.id,
      timer(SYNC_POLL_MS, SYNC_POLL_MS)
        .pipe(
          take(SYNC_POLL_COUNT),
          switchMap(() => this.api.jellyfin.list()),
          tap((accounts) => this.accounts.set(accounts)),
          takeWhile((accounts) => accounts.find(({ id }) => id === account.id)?.last_sync_at === account.last_sync_at),
        )
        .subscribe({ error: () => undefined }),
    );
  }

  unlink(account: Model.Http.JellyfinAccount): void {
    this.accounts.update((accounts = []) => accounts.filter(({ id }) => id !== account.id));
    this.api.jellyfin.unlink(account.id).subscribe({
      error: () => {
        this.accounts.update((accounts = []) => [...accounts, account]);
        this.notify('app.profile.jellyfin.unlinkFailed');
      },
    });
  }

  sync(account: Model.Http.JellyfinAccount): void {
    this.api.jellyfin.sync(account.id).subscribe({
      next: () => {
        this.notify('app.profile.jellyfin.syncQueued');
        this.followSync(account);
      },
      error: () => this.notify('app.profile.jellyfin.syncFailed'),
    });
  }

  /** A linked account is synced at once by the server: its line follows that first sync. */
  private add(linked: Model.Http.JellyfinAccount): void {
    this.accounts.update((accounts = []) => [...accounts.filter(({ id }) => id !== linked.id), linked]);
    this.followSync(linked);
  }

  private notify(path: TranslationPath<'app'>): void {
    this.showMessage(this.translate(path));
  }
}
