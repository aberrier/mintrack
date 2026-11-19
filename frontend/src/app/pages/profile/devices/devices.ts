import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { MatButton } from '@angular/material/button';
import { ApiService } from '../../../core/api/api.service';
import { AuthStore } from '../../../core/auth/auth.store';
import { formatDate } from '../../../core/dates';
import { injectTranslator } from '../../../core/i18n';
import { injectNotify } from '../../../core/notify';

/** The devices signed in to the account, this one first marked as such; any other one can be signed out. */
@Component({
  selector: 'app-devices',
  imports: [MatButton],
  template: `
    @if (sessions.hasValue()) {
      <ul class="flex flex-col" [attr.aria-label]="translate('app.profile.devices.title')">
        @for (session of sessions.value(); track session.id) {
          <li class="flex min-h-14 items-center gap-2" data-testid="device">
            <div class="flex min-w-0 grow flex-col">
              <span class="truncate [font:var(--mat-sys-body-large)]">{{
                session.device ?? translate('app.profile.devices.unknown')
              }}</span>
              <span class="text-on-surface-variant [font:var(--mat-sys-body-medium)]">
                @if (session.current) {
                  {{ translate('app.profile.devices.current') }}
                } @else {
                  {{ translate('app.profile.devices.lastActive', { date: date(session.last_used_at) }) }}
                }
              </span>
            </div>
            @if (!session.current) {
              <button
                matButton
                type="button"
                class="min-h-12"
                [attr.aria-label]="
                  translate('app.profile.devices.logOutLabel', {
                    device: session.device ?? translate('app.profile.devices.unknown'),
                  })
                "
                (click)="logOut(session)">
                {{ translate('app.profile.devices.logOut') }}
              </button>
            }
          </li>
        }
      </ul>
    } @else if (sessions.error()) {
      <p class="text-on-surface-variant [font:var(--mat-sys-body-medium)]">
        {{ translate('app.profile.devices.loadFailed') }}
      </p>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Devices {
  protected readonly translate = injectTranslator('app');
  private readonly api = inject(ApiService);
  private readonly timeZone = inject(AuthStore).$timeZone;
  private readonly notify = injectNotify();

  protected readonly sessions = rxResource({ stream: () => this.api.auth.sessions() });

  protected logOut(session: Model.Http.Session): void {
    this.api.auth.deleteSession(session.id).subscribe({
      next: () => this.sessions.reload(),
      error: () => this.notify(this.translate('app.profile.devices.logOutFailed')),
    });
  }

  protected date(value: string): string {
    return formatDate(value, this.timeZone());
  }
}
