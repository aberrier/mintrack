import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { AbstractControl, NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatError, MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../core/api/api.service';
import { AuthStore } from '../../core/auth/auth.store';
import { safeNext } from '../../core/auth/guards';
import { injectTranslator, TranslationPath } from '../../core/i18n';
import { newPasswordValidators, usernameValidators } from '../../shared/validators';

/** The confirmation must repeat the password next to it. */
function samePassword(control: AbstractControl<string>): { mismatch: true } | null {
  return control.value === control.parent?.get('password')?.value ? null : { mismatch: true };
}

/** Logs in; while no account exists at all, creates the admin account instead. */
@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, MatFormField, MatLabel, MatHint, MatError, MatInput, MatButton],
  templateUrl: './login.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Login {
  protected readonly translate = injectTranslator('app');
  private readonly api = inject(ApiService);
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(NonNullableFormBuilder);

  /** Whether the admin account can still be created; the login form shows if the server cannot say. */
  protected readonly setup = rxResource({ stream: () => this.api.auth.setupState() });
  protected readonly form = this.fb.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });
  protected readonly setupForm = this.fb.group({
    username: ['', usernameValidators],
    password: ['', newPasswordValidators],
    confirm: ['', [Validators.required, samePassword]],
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
      await this.openNext();
    } catch (error: unknown) {
      this.$error.set(loginError(error));
    } finally {
      this.$busy.set(false);
    }
  }

  protected async createAdmin(): Promise<void> {
    // The password may have changed since the confirmation was typed.
    this.setupForm.controls.confirm.updateValueAndValidity();
    if (this.setupForm.invalid || this.$busy()) return;
    this.$busy.set(true);
    this.$error.set(null);
    const { username, password } = this.setupForm.getRawValue();
    try {
      await this.store.setUp(username, password);
      await this.openNext();
    } catch (error: unknown) {
      const closed = error instanceof HttpErrorResponse && error.status === 409;
      this.$error.set(closed ? 'app.setup.closed' : loginError(error));
      if (closed) this.setup.reload();
    } finally {
      this.$busy.set(false);
    }
  }

  /** The page asked for before logging in, or the watch list. */
  private openNext(): Promise<boolean> {
    return this.router.navigateByUrl(safeNext(this.route.snapshot.queryParamMap.get('next')));
  }
}

function loginError(error: unknown): TranslationPath<'app'> {
  if (error instanceof HttpErrorResponse && error.status === 401) return 'app.login.errors.wrong';
  if (error instanceof HttpErrorResponse && error.status === 429) return 'app.login.errors.rateLimited';
  return 'app.errors.unknown';
}
