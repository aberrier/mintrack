import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormGroupDirective, NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatError, MatFormField, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { finalize } from 'rxjs';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { JellyfinStore } from '../../../core/jellyfin/jellyfin.store';

const linkErrors: Record<Model.Http.JellyfinLinkError, TranslationPath<'app'>> = {
  jellyfin_invalid_credentials: 'app.profile.jellyfin.errors.invalidCredentials',
  jellyfin_forbidden_address: 'app.profile.jellyfin.errors.forbiddenAddress',
  jellyfin_unreachable: 'app.profile.jellyfin.errors.unreachable',
  jellyfin_redirected: 'app.profile.jellyfin.errors.redirected',
  jellyfin_bad_response: 'app.profile.jellyfin.errors.badResponse',
};

const syncFailures: Record<Exclude<Model.Http.JellyfinSyncStatus, 'ok'>, TranslationPath<'app'>> = {
  unreachable: 'app.profile.jellyfin.status.unreachable',
  unauthorized: 'app.profile.jellyfin.status.unauthorized',
  failed: 'app.profile.jellyfin.status.failed',
};

/** Link Jellyfin accounts, see how their last sync went, sync or unlink them. */
@Component({
  selector: 'app-jellyfin-accounts',
  imports: [ReactiveFormsModule, DatePipe, MatButton, MatFormField, MatLabel, MatInput, MatError],
  templateUrl: './jellyfin-accounts.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JellyfinAccounts {
  protected readonly translate = injectTranslator('app');
  protected readonly store = inject(JellyfinStore);
  protected readonly syncFailures = syncFailures;

  protected readonly form = inject(NonNullableFormBuilder).group({
    server_url: ['', [Validators.required, Validators.pattern(/^https?:\/\/\S+$/)]],
    username: ['', Validators.required],
    password: [''],
  });
  protected readonly $linking = signal(false);
  protected readonly $linkError = signal<TranslationPath<'app'> | undefined>(undefined);

  constructor() {
    this.store.load();
  }

  protected link(formDirective: FormGroupDirective): void {
    if (this.form.invalid || this.$linking()) return;
    this.$linking.set(true);
    this.$linkError.set(undefined);
    this.store
      .link(this.form.getRawValue())
      .pipe(finalize(() => this.$linking.set(false)))
      .subscribe({
        // Through the directive, so the reset form is no longer "submitted" and shows no errors.
        next: () => formDirective.resetForm(),
        error: (error: unknown) => this.$linkError.set(linkErrorPath(error)),
      });
  }
}

function linkErrorPath(error: unknown): TranslationPath<'app'> {
  if (!(error instanceof HttpErrorResponse)) return 'app.profile.jellyfin.errors.unknown';
  const detail: unknown = (error.error as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string' && detail in linkErrors) return linkErrors[detail as Model.Http.JellyfinLinkError];
  if (error.status === 422) return 'app.profile.jellyfin.errors.invalidAddress';
  return 'app.profile.jellyfin.errors.unknown';
}
