import { HttpErrorResponse } from '@angular/common/http';
import { afterNextRender, ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { ActivatedRoute, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { ApiService } from '../../core/api/api.service';
import { AuthStore } from '../../core/auth/auth.store';
import { injectTranslator, TranslationPath } from '../../core/i18n';

/** Sets a password from an invitation or reset link: /password#<token>. */
@Component({
  selector: 'app-password',
  imports: [ReactiveFormsModule, MatFormField, MatLabel, MatHint, MatInput, MatButton],
  templateUrl: './password.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Password {
  protected readonly translate = injectTranslator('app');
  private readonly api = inject(ApiService);
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly token = inject(ActivatedRoute).snapshot.fragment ?? '';

  protected readonly link = rxResource({
    params: () => this.token,
    stream: ({ params: token }) => this.api.auth.describeLink(token),
  });
  protected readonly $error = signal<TranslationPath<'app'> | null>(null);
  protected readonly $busy = signal(false);

  protected readonly form = inject(NonNullableFormBuilder).group({
    password: ['', [Validators.required, Validators.minLength(15), Validators.maxLength(128)]],
  });

  constructor() {
    // The token leaves the address bar and the history once read.
    afterNextRender(() => void this.router.navigateByUrl(appRoutes.password(), { replaceUrl: true }));
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.$busy() || !this.link.hasValue()) return;
    this.$busy.set(true);
    this.$error.set(null);
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    try {
      const user = await firstValueFrom(this.api.auth.useLink(this.token, this.form.getRawValue().password, timezone));
      this.store.set(user);
      await this.router.navigateByUrl(appRoutes.watchList());
    } catch (error: unknown) {
      const invalid = error instanceof HttpErrorResponse && error.status === 400;
      this.$error.set(invalid ? 'app.password.invalid' : 'app.errors.unknown');
    } finally {
      this.$busy.set(false);
    }
  }
}
