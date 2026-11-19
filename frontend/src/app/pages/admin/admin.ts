import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { rxResource, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormGroupDirective, NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton, MatIconButton } from '@angular/material/button';
import { MatError, MatFormField, MatHint, MatLabel, MatPrefix } from '@angular/material/form-field';
import { MatIcon } from '@angular/material/icon';
import { MatInput } from '@angular/material/input';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../core/api/api.service';
import { AuthStore } from '../../core/auth/auth.store';
import { injectCopy } from '../../core/copy';
import { formatDateTime } from '../../core/dates';
import { injectTranslator, TranslationPath } from '../../core/i18n';
import { injectNotify } from '../../core/notify';
import { LoadError } from '../../shared/load-error';

interface ShownLink {
  username: string;
  link: string;
}

/**
 * The Admin tab: invite someone (their password link is shown once, to copy and send), and manage the users: a new
 * password link, disable or enable (others only).
 */
@Component({
  selector: 'app-admin',
  imports: [
    ReactiveFormsModule,
    MatFormField,
    MatLabel,
    MatHint,
    MatError,
    MatInput,
    MatButton,
    MatIconButton,
    MatIcon,
    MatPrefix,
    LoadError,
  ],
  templateUrl: './admin.html',
  styles: `
    .user {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 16px;
      border-radius: var(--mat-sys-corner-large);
      background: var(--mat-sys-surface-container-low);
    }
    .tag {
      padding: 2px 8px;
      border-radius: var(--mat-sys-corner-small);
      background: var(--mat-sys-surface-container-high);
      color: var(--mat-sys-on-surface-variant);
      font: var(--mat-sys-label-large);
    }
    .tag.active {
      background: var(--mat-sys-secondary-container);
      color: var(--mat-sys-on-secondary-container);
    }
    .tag.disabled {
      background: var(--mat-sys-error-container);
      color: var(--mat-sys-on-error-container);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Admin {
  protected readonly translate = injectTranslator('app');
  private readonly api = inject(ApiService);
  private readonly timeZone = inject(AuthStore).$timeZone;
  /** The admin using the page, who cannot disable themselves and be locked out. */
  protected readonly $me = inject(AuthStore).$user;
  private readonly notify = injectNotify();
  private readonly copyText = injectCopy();

  protected readonly statusLabels: Record<Model.Http.UserStatus, TranslationPath<'app'>> = {
    invited: 'app.admin.status.invited',
    invitation_expired: 'app.admin.status.invitation_expired',
    active: 'app.admin.status.active',
    disabled: 'app.admin.status.disabled',
  };
  protected readonly users = rxResource({ stream: () => this.api.adminUsers.list() });
  /** The search field's text: the list keeps the users whose name contains it, ignoring case. */
  protected readonly $search = signal('');
  protected readonly $shownUsers = computed(() => {
    const search = this.$search().trim().toLowerCase();
    const users = this.users.value() ?? [];
    return search ? users.filter((user) => user.username.toLowerCase().includes(search)) : users;
  });
  protected readonly $shownLink = signal<ShownLink | null>(null);
  protected readonly $taken = signal(false);
  protected readonly $busy = signal(false);
  protected readonly form = inject(NonNullableFormBuilder).group({
    username: ['', [Validators.required, Validators.pattern(/^[A-Za-z0-9._-]{1,150}$/)]],
  });

  constructor() {
    // A name being typed again is no longer the one found taken.
    this.form.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.$taken.set(false));
  }

  protected lastSeen(user: Model.Http.AdminUser): string {
    return user.last_seen_at
      ? this.translate('app.admin.lastSeen', { date: formatDateTime(user.last_seen_at, this.timeZone()) })
      : this.translate('app.admin.neverSeen');
  }

  protected async create(formDirective: FormGroupDirective): Promise<void> {
    if (this.form.invalid || this.$busy()) return;
    this.$busy.set(true);
    const { username } = this.form.getRawValue();
    try {
      const created = await firstValueFrom(this.api.adminUsers.create(username));
      this.$shownLink.set({ username: created.user.username, link: created.link });
      formDirective.resetForm();
      this.users.reload();
    } catch (error: unknown) {
      if (error instanceof HttpErrorResponse && error.status === 409) this.$taken.set(true);
      else this.notify(this.translate('app.errors.unknown'));
    } finally {
      this.$busy.set(false);
    }
  }

  protected async newLink(user: Model.Http.AdminUser): Promise<void> {
    try {
      const { link } = await firstValueFrom(this.api.adminUsers.newLink(user.id));
      this.$shownLink.set({ username: user.username, link });
    } catch {
      this.notify(this.translate('app.errors.unknown'));
    }
    this.users.reload();
  }

  protected async setActive(user: Model.Http.AdminUser, isActive: boolean): Promise<void> {
    try {
      await firstValueFrom(this.api.adminUsers.setActive(user.id, isActive));
    } catch (error: unknown) {
      const lastAdmin = error instanceof HttpErrorResponse && error.status === 409;
      this.notify(this.translate(lastAdmin ? 'app.admin.lastAdmin' : 'app.errors.unknown'));
    }
    this.users.reload();
  }

  protected copy(link: string): void {
    this.copyText(link, 'app.admin.link.copied');
  }
}
