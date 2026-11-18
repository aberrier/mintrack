import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthStore } from '../../core/auth/auth.store';
import { safeNext } from '../../core/auth/guards';
import { injectTranslator, TranslationPath } from '../../core/i18n';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, MatFormField, MatLabel, MatInput, MatButton],
  templateUrl: './login.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Login {
  protected readonly translate = injectTranslator('app');
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly form = inject(NonNullableFormBuilder).group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });
  protected readonly $error = signal<TranslationPath<'app'> | null>(null);
  protected readonly $busy = signal(false);

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.$busy()) return;
    this.$busy.set(true);
    this.$error.set(null);
    const { username, password } = this.form.getRawValue();
    try {
      await this.store.login(username, password);
      await this.router.navigateByUrl(safeNext(this.route.snapshot.queryParamMap.get('next')));
    } catch (error: unknown) {
      this.$error.set(loginError(error));
    } finally {
      this.$busy.set(false);
    }
  }
}

function loginError(error: unknown): TranslationPath<'app'> {
  if (error instanceof HttpErrorResponse && error.status === 401) return 'app.login.errors.wrong';
  if (error instanceof HttpErrorResponse && error.status === 429) return 'app.login.errors.rateLimited';
  return 'app.errors.unknown';
}
