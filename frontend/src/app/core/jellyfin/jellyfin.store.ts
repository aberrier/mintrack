import { inject, Injectable, signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable, tap } from 'rxjs';
import { ApiService } from '../api/api.service';
import { injectTranslator, TranslationPath } from '../i18n';

/** The signed-in user's linked Jellyfin accounts. */
@Injectable({ providedIn: 'root' })
export class JellyfinStore {
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = injectTranslator('app');

  private readonly accounts = signal<Model.Http.JellyfinAccount[] | undefined>(undefined);
  readonly $accounts = this.accounts.asReadonly();

  load(): void {
    this.api.jellyfin.list().subscribe({
      next: (accounts) => this.accounts.set(accounts),
      error: () => this.notify('app.profile.jellyfin.loadFailed'),
    });
  }

  /** Errors are left to the caller, which shows them next to the form. */
  link(request: Model.Http.JellyfinLinkRequest): Observable<Model.Http.JellyfinAccount> {
    return this.api.jellyfin
      .link(request)
      .pipe(
        tap((linked) =>
          this.accounts.update((accounts = []) => [...accounts.filter(({ id }) => id !== linked.id), linked]),
        ),
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
      next: () => this.notify('app.profile.jellyfin.syncQueued'),
      error: () => this.notify('app.profile.jellyfin.syncFailed'),
    });
  }

  private notify(path: TranslationPath<'app'>): void {
    this.snackBar.open(this.translate(path), undefined, { duration: 4000 });
  }
}
