import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { switchMap } from 'rxjs';
import { appRoutes } from '../../../app.paths';
import { ApiService } from '../../../core/api/api.service';
import { AuthStore } from '../../../core/auth/auth.store';
import { injectCopy } from '../../../core/copy';
import { formatDate } from '../../../core/dates';
import { injectTranslator } from '../../../core/i18n';
import { injectNotify } from '../../../core/notify';
import { injectConfirm } from '../../../shared/confirm-dialog';

/** The user's API tokens for the MCP server: create one (shown once), list them, revoke one. */
@Component({
  selector: 'app-api-tokens',
  imports: [ReactiveFormsModule, RouterLink, MatButton, MatFormField, MatLabel, MatInput],
  templateUrl: './api-tokens.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApiTokens {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  private readonly api = inject(ApiService);
  private readonly timeZone = inject(AuthStore).$timeZone;
  private readonly confirm = injectConfirm();
  private readonly notify = injectNotify();
  private readonly copyText = injectCopy();

  protected readonly tokens = rxResource({ stream: () => this.api.apiTokens.list() });
  protected readonly name = new FormControl('', { nonNullable: true });
  protected readonly $created = signal<Model.Http.CreatedApiToken | null>(null);
  protected readonly $creating = signal(false);

  protected create(): void {
    const name = this.name.value.trim();
    if (!name) return;
    this.$creating.set(true);
    this.api.apiTokens.create(name).subscribe({
      next: (created) => {
        this.$created.set(created);
        this.name.reset();
        this.$creating.set(false);
        this.tokens.reload();
      },
      error: () => {
        this.$creating.set(false);
        this.notify(this.translate('app.profile.apiTokens.createFailed'));
      },
    });
  }

  protected copy(token: string): void {
    this.copyText(token, 'app.profile.apiTokens.copied');
  }

  protected revoke(token: Model.Http.ApiToken): void {
    this.confirm({
      title: this.translate('app.profile.apiTokens.confirmTitle'),
      message: this.translate('app.profile.apiTokens.confirmText', { name: token.name }),
      confirm: this.translate('app.profile.apiTokens.revoke'),
    })
      .pipe(switchMap(() => this.api.apiTokens.revoke(token.id)))
      .subscribe({
        next: () => this.tokens.reload(),
        error: () => this.notify(this.translate('app.profile.apiTokens.revokeFailed')),
      });
  }

  protected date(value: string): string {
    return formatDate(value, this.timeZone());
  }
}
