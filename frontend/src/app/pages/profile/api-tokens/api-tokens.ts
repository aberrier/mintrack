import { Clipboard } from '@angular/cdk/clipboard';
import { ChangeDetectionStrategy, Component, inject, signal, TemplateRef, viewChild } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import {
  MatDialog,
  MatDialogActions,
  MatDialogClose,
  MatDialogContent,
  MatDialogTitle,
} from '@angular/material/dialog';
import { MatFormField, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';
import { filter, switchMap } from 'rxjs';
import { ApiService } from '../../../core/api/api.service';
import { injectTranslator, TranslationPath } from '../../../core/i18n';

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

/** The user's API tokens for the MCP server: create one (shown once), list them, revoke one. */
@Component({
  selector: 'app-api-tokens',
  imports: [
    ReactiveFormsModule,
    MatButton,
    MatFormField,
    MatLabel,
    MatInput,
    MatDialogTitle,
    MatDialogContent,
    MatDialogActions,
    MatDialogClose,
  ],
  templateUrl: './api-tokens.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApiTokens {
  protected readonly translate = injectTranslator('app');
  private readonly api = inject(ApiService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly clipboard = inject(Clipboard);
  private readonly confirmRevoke = viewChild.required<TemplateRef<unknown>>('confirmRevoke');

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
        this.notify('app.profile.apiTokens.createFailed');
      },
    });
  }

  protected copy(token: string): void {
    if (this.clipboard.copy(token)) this.notify('app.profile.apiTokens.copied');
  }

  protected revoke(token: Model.Http.ApiToken): void {
    this.dialog
      .open<unknown, Model.Http.ApiToken, boolean>(this.confirmRevoke(), { data: token })
      .afterClosed()
      .pipe(
        filter(Boolean),
        switchMap(() => this.api.apiTokens.revoke(token.id)),
      )
      .subscribe({
        next: () => this.tokens.reload(),
        error: () => this.notify('app.profile.apiTokens.revokeFailed'),
      });
  }

  protected date(value: string): string {
    return dateFormat.format(new Date(value));
  }

  private notify(path: TranslationPath<'app'>): void {
    this.snackBar.open(this.translate(path), undefined, { duration: 4000 });
  }
}
