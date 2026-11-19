import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormGroupDirective, NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatError, MatFormField, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { MatProgressBar } from '@angular/material/progress-bar';
import { filter, finalize, first, Subscription, switchMap, timer } from 'rxjs';
import { ApiService } from '../../../core/api/api.service';
import { AuthStore } from '../../../core/auth/auth.store';
import { injectCopy } from '../../../core/copy';
import { formatDateTime } from '../../../core/dates';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { JellyfinStore } from '../../../core/jellyfin/jellyfin.store';
import { unmatchedDetails } from '../../../core/jellyfin/unmatched';
import { injectNotify } from '../../../core/notify';

/** Milliseconds between two questions to Jellyfin about whether the code was approved. */
export const QUICK_CONNECT_POLL_MS = 3000;

const linkErrors: Record<Model.Http.JellyfinLinkError, TranslationPath<'app'>> = {
  jellyfin_invalid_credentials: 'app.profile.jellyfin.errors.invalidCredentials',
  jellyfin_unreachable: 'app.profile.jellyfin.errors.unreachable',
  jellyfin_redirected: 'app.profile.jellyfin.errors.redirected',
  jellyfin_bad_response: 'app.profile.jellyfin.errors.badResponse',
  jellyfin_quick_connect_disabled: 'app.profile.jellyfin.errors.quickConnectDisabled',
  jellyfin_quick_connect_pending: 'app.profile.jellyfin.errors.quickConnectPending',
};

const syncFailures: Record<Exclude<Model.Http.JellyfinSyncStatus, 'ok'>, TranslationPath<'app'>> = {
  unreachable: 'app.profile.jellyfin.status.unreachable',
  unauthorized: 'app.profile.jellyfin.status.unauthorized',
  failed: 'app.profile.jellyfin.status.failed',
};

/** How the link form stands: the server's address, the Quick Connect code waiting for approval, or a password. */
type Step = 'address' | 'code' | 'password';

/**
 * Link Jellyfin accounts, see how their last sync went, sync or unlink them. Linking uses Quick Connect: MinTrack
 * shows a code, the user approves it in a Jellyfin app, and no password reaches MinTrack. A server with Quick
 * Connect turned off falls back to the username and password, which MinTrack uses once and forgets.
 */
@Component({
  selector: 'app-jellyfin-accounts',
  imports: [
    NgTemplateOutlet,
    ReactiveFormsModule,
    MatButton,
    MatFormField,
    MatLabel,
    MatInput,
    MatError,
    MatProgressBar,
  ],
  templateUrl: './jellyfin-accounts.html',
  styles: `
    .code {
      font: var(--mat-sys-headline-small);
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.2em;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JellyfinAccounts {
  protected readonly translate = injectTranslator('app');
  protected readonly store = inject(JellyfinStore);
  private readonly api = inject(ApiService);
  private readonly timeZone = inject(AuthStore).$timeZone;
  private readonly notify = injectNotify();
  private readonly copyText = injectCopy();
  private readonly destroyRef = inject(DestroyRef);
  protected readonly syncFailures = syncFailures;

  private readonly forms = inject(NonNullableFormBuilder);
  protected readonly serverUrl = this.forms.control('', [Validators.required, Validators.pattern(/^https?:\/\/\S+$/)]);
  protected readonly credentials = this.forms.group({
    username: ['', Validators.required],
    password: [''],
  });
  protected readonly $step = signal<Step>('address');
  protected readonly $code = signal<string | null>(null);
  protected readonly $busy = signal(false);
  protected readonly $error = signal<TranslationPath<'app'> | undefined>(undefined);
  private waiting?: Subscription;

  constructor() {
    this.store.load();
    // A new address or new credentials make an old error irrelevant.
    this.serverUrl.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.$error.set(undefined));
    this.credentials.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.$error.set(undefined));
  }

  protected date(value: string): string {
    return formatDateTime(value, this.timeZone());
  }

  /** Copy what Jellyfin says of the items not recognized, for a bug report. */
  protected copyDetails(account: Model.Http.JellyfinAccount): void {
    this.copyText(unmatchedDetails(account), 'app.profile.jellyfin.detailsCopied');
  }

  protected syncedLine(account: Model.Http.JellyfinAccount, lastSync: string): string {
    const params = { date: this.date(lastSync), count: String(account.last_sync_imported) };
    return this.translate(
      account.last_sync_imported === 1 ? 'app.profile.jellyfin.lastSyncOne' : 'app.profile.jellyfin.lastSync',
      params,
    );
  }

  /** Ask the server for a Quick Connect code, then wait for its approval and link the account. */
  protected getCode(): void {
    if (this.serverUrl.invalid || this.$busy()) {
      this.serverUrl.markAsTouched();
      return;
    }
    const server = { server_url: this.serverUrl.value };
    this.$busy.set(true);
    this.$error.set(undefined);
    this.api.jellyfin
      .startQuickConnect(server)
      .pipe(finalize(() => this.$busy.set(false)))
      .subscribe({
        next: ({ code, secret }) => {
          this.$code.set(code);
          this.$step.set('code');
          this.waitForApproval({ ...server, secret });
        },
        error: (error: unknown) => {
          const path = linkErrorPath(error);
          if (path === 'app.profile.jellyfin.errors.quickConnectDisabled') this.$step.set('password');
          this.$error.set(path);
        },
      });
  }

  protected linkWithPassword(formDirective: FormGroupDirective): void {
    if (this.serverUrl.invalid || this.credentials.invalid || this.$busy()) {
      this.serverUrl.markAsTouched();
      return;
    }
    this.$busy.set(true);
    this.$error.set(undefined);
    this.store
      .link({ server_url: this.serverUrl.value, ...this.credentials.getRawValue() })
      .pipe(finalize(() => this.$busy.set(false)))
      .subscribe({
        next: () => {
          // Through the directive, so the reset form is no longer "submitted" and shows no errors.
          formDirective.resetForm();
          this.linked();
        },
        error: (error: unknown) => this.$error.set(linkErrorPath(error)),
      });
  }

  /** Back to the address, leaving a code that is waiting or the password form. */
  protected restart(step: Step = 'address'): void {
    this.waiting?.unsubscribe();
    this.$code.set(null);
    this.$error.set(undefined);
    this.$step.set(step);
  }

  private waitForApproval(request: Model.Http.QuickConnectRequest): void {
    this.waiting?.unsubscribe();
    this.waiting = timer(QUICK_CONNECT_POLL_MS, QUICK_CONNECT_POLL_MS)
      .pipe(
        switchMap(() => this.api.jellyfin.quickConnectState(request)),
        filter(({ approved }) => approved),
        first(),
        switchMap(() => {
          this.$busy.set(true);
          return this.store.linkQuickConnect(request).pipe(finalize(() => this.$busy.set(false)));
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => this.linked(),
        error: (error: unknown) => {
          this.restart();
          this.$error.set(linkErrorPath(error));
        },
      });
  }

  private linked(): void {
    this.restart();
    this.serverUrl.reset();
    this.credentials.reset();
    this.notify(this.translate('app.profile.jellyfin.linked'));
  }
}

function linkErrorPath(error: unknown): TranslationPath<'app'> {
  if (!(error instanceof HttpErrorResponse)) return 'app.profile.jellyfin.errors.unknown';
  const detail: unknown = (error.error as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string' && detail in linkErrors) return linkErrors[detail as Model.Http.JellyfinLinkError];
  if (error.status === 422) return 'app.profile.jellyfin.errors.invalidAddress';
  return 'app.profile.jellyfin.errors.unknown';
}
