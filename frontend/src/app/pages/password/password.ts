import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal, signal } from '@angular/core';
import { rxResource, toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { MatError, MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { ApiService } from '../../core/api/api.service';
import { AuthStore } from '../../core/auth/auth.store';
import { browserTimeZone } from '../../core/dates';
import { injectTranslator, TranslationPath } from '../../core/i18n';
import { newPasswordValidators } from '../../shared/validators';

/** Offline, or nothing answers for the server (a proxy's 502 to 504). */
const UNREACHABLE_STATUSES = [0, 502, 503, 504];

/** Why the server refused the link, if that is what the error says. */
function linkProblem(error: unknown): Model.Http.LinkProblem | null {
  if (!(error instanceof HttpErrorResponse) || error.status !== 400) return null;
  return (error.error as Partial<Model.Http.LinkRefused> | null)?.reason ?? 'invalid';
}

function failure(error: unknown): TranslationPath<'app'> {
  const status = error instanceof HttpErrorResponse ? error.status : 0;
  if (status === 422) return 'app.common.passwordHint';
  return UNREACHABLE_STATUSES.includes(status) ? 'app.password.unreachable' : 'app.errors.unknown';
}

/**
 * Sets a password from an invitation or reset link: /password#<token>. The token stays in the address until the
 * password is set, so a reload, a restored tab or "Open in browser" from a messaging app still has it; only setting
 * the password consumes the link.
 */
@Component({
  selector: 'app-password',
  imports: [ReactiveFormsModule, RouterLink, MatFormField, MatLabel, MatHint, MatError, MatInput, MatButton],
  templateUrl: './password.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Password {
  protected readonly translate = injectTranslator('app');
  private readonly api = inject(ApiService);
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  /** Another link opened in the same tab changes only the fragment, which keeps this page. */
  private readonly fragment = toSignal(this.route.fragment, { initialValue: this.route.snapshot.fragment });
  protected readonly $token = computed(() => this.fragment() ?? '');
  protected readonly loginUrl = appRoutes.login();
  protected readonly problemTexts: Record<Model.Http.LinkProblem, TranslationPath<'app'>> = {
    invalid: 'app.password.problems.invalid',
    expired: 'app.password.problems.expired',
    used: 'app.password.problems.used',
    replaced: 'app.password.problems.replaced',
  };

  protected readonly link = rxResource({
    params: () => this.$token() || undefined,
    stream: ({ params: token }) => this.api.auth.describeLink(token),
  });
  /** The link's refusal, from setting the password. */
  private readonly refusedOnSubmit = linkedSignal<string, Model.Http.LinkProblem | null>({
    source: this.$token,
    computation: () => null,
  });
  protected readonly $problem = computed(() => this.refusedOnSubmit() ?? linkProblem(this.link.error()));
  /** Why the link could not be checked, when the server did not refuse it. */
  protected readonly $checkFailure = computed(() => {
    const error = this.link.error();
    return error && !this.$problem() ? failure(error) : null;
  });
  protected readonly $error = signal<TranslationPath<'app'> | null>(null);
  protected readonly $busy = signal(false);

  protected readonly form = inject(NonNullableFormBuilder).group({
    password: ['', newPasswordValidators],
  });

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.$busy() || !this.link.hasValue()) return;
    this.$busy.set(true);
    this.$error.set(null);
    const { password } = this.form.getRawValue();
    try {
      const user = await firstValueFrom(this.api.auth.useLink(this.$token(), password, browserTimeZone()));
      this.store.set(user);
      // The used token leaves the address and the history.
      await this.router.navigateByUrl(appRoutes.watchList(), { replaceUrl: true });
    } catch (error: unknown) {
      const problem = linkProblem(error);
      if (problem) this.refusedOnSubmit.set(problem);
      else this.$error.set(failure(error));
    } finally {
      this.$busy.set(false);
    }
  }
}
