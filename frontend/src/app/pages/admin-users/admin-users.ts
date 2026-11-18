import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton, MatIconButton } from '@angular/material/button';
import { MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatIcon } from '@angular/material/icon';
import { MatInput } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../core/api/api.service';
import { injectTranslator, TranslationPath } from '../../core/i18n';

interface ShownLink {
  username: string;
  link: string;
}

/** Admins invite users, give them a new password link, and disable or re-enable them. */
@Component({
  selector: 'app-admin-users',
  imports: [
    ReactiveFormsModule,
    DatePipe,
    MatFormField,
    MatLabel,
    MatHint,
    MatInput,
    MatButton,
    MatIconButton,
    MatIcon,
  ],
  templateUrl: './admin-users.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class AdminUsers {
  protected readonly translate = injectTranslator('app');
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);

  protected readonly statusLabels: Record<Model.Http.UserStatus, TranslationPath<'app'>> = {
    invited: 'app.adminUsers.status.invited',
    invitation_expired: 'app.adminUsers.status.invitation_expired',
    active: 'app.adminUsers.status.active',
    disabled: 'app.adminUsers.status.disabled',
  };
  protected readonly users = rxResource({ stream: () => this.api.adminUsers.list() });
  protected readonly $shownLink = signal<ShownLink | null>(null);
  protected readonly $taken = signal(false);
  protected readonly $busy = signal(false);
  protected readonly form = inject(NonNullableFormBuilder).group({
    username: ['', [Validators.required, Validators.pattern(/^[A-Za-z0-9._-]{1,150}$/)]],
  });

  protected async create(): Promise<void> {
    if (this.form.invalid || this.$busy()) return;
    this.$busy.set(true);
    this.$taken.set(false);
    const { username } = this.form.getRawValue();
    try {
      const created = await firstValueFrom(this.api.adminUsers.create(username));
      this.$shownLink.set({ username: created.user.username, link: created.link });
      this.form.reset();
      this.users.reload();
    } catch (error: unknown) {
      if (error instanceof HttpErrorResponse && error.status === 409) this.$taken.set(true);
      else this.notify('app.errors.unknown');
    } finally {
      this.$busy.set(false);
    }
  }

  protected async newLink(user: Model.Http.AdminUser): Promise<void> {
    try {
      const { link } = await firstValueFrom(this.api.adminUsers.newLink(user.id));
      this.$shownLink.set({ username: user.username, link });
    } catch {
      this.notify('app.errors.unknown');
    }
    this.users.reload();
  }

  protected async setActive(user: Model.Http.AdminUser, isActive: boolean): Promise<void> {
    try {
      await firstValueFrom(this.api.adminUsers.setActive(user.id, isActive));
    } catch (error: unknown) {
      const lastAdmin = error instanceof HttpErrorResponse && error.status === 409;
      this.notify(lastAdmin ? 'app.adminUsers.lastAdmin' : 'app.errors.unknown');
    }
    this.users.reload();
  }

  protected async copy(link: string): Promise<void> {
    await navigator.clipboard.writeText(link);
    this.notify('app.adminUsers.link.copied');
  }

  private notify(message: TranslationPath<'app'>): void {
    this.snackBar.open(this.translate(message), undefined, { duration: 4000 });
  }
}
