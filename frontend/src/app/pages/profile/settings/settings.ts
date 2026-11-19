import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal, viewChild } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatAutocomplete, MatAutocompleteTrigger, MatOption } from '@angular/material/autocomplete';
import { MatButton } from '@angular/material/button';
import { MatError, MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { firstValueFrom } from 'rxjs';
import { appRoutes } from '../../../app.paths';
import { ApiService } from '../../../core/api/api.service';
import { AuthStore } from '../../../core/auth/auth.store';
import { zoneWithOffset } from '../../../core/dates';
import { injectTranslator } from '../../../core/i18n';
import { injectNotify } from '../../../core/notify';
import { PushStore } from '../../../core/push/push.store';
import { BackButton } from '../../../shared/back-button';
import { newPasswordValidators } from '../../../shared/validators';
import { ApiTokens } from '../api-tokens/api-tokens';
import { Devices } from '../devices/devices';
import { ImportCard } from '../import-card/import-card';
import { JellyfinAccounts } from '../jellyfin-accounts/jellyfin-accounts';
import { PushSettings } from '../push-settings/push-settings';

/** How a zone is searched: lower case, spaces as underscores ("new york" finds America/New_York). */
function searchable(text: string): string {
  return text.trim().toLowerCase().replaceAll(' ', '_');
}

/** A zone with its offset, or the text as typed when it names no zone. */
function zoneLabel(zone: string): string {
  try {
    return zoneWithOffset(zone);
  } catch {
    return zone;
  }
}

/**
 * The user's settings in groups: account, notifications, integrations, import history, then the devices signed in,
 * with logging out.
 */
@Component({
  selector: 'app-settings',
  imports: [
    ReactiveFormsModule,
    MatFormField,
    MatLabel,
    MatHint,
    MatError,
    MatInput,
    MatButton,
    MatAutocomplete,
    MatAutocompleteTrigger,
    MatOption,
    BackButton,
    PushSettings,
    JellyfinAccounts,
    ImportCard,
    ApiTokens,
    Devices,
  ],
  templateUrl: './settings.html',
  styles: `
    /* A group of settings: its name in the style of the app's section labels, then its cards. */
    .group {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .group-title {
      color: var(--mat-sys-on-surface-variant);
      font: var(--mat-sys-title-small);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Settings {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  private readonly api = inject(ApiService);
  private readonly store = inject(AuthStore);
  private readonly push = inject(PushStore);
  private readonly notify = injectNotify();
  private readonly forms = inject(NonNullableFormBuilder);

  protected readonly $user = this.store.$user;

  protected readonly about = rxResource({ stream: () => this.api.about() });

  protected readonly timezone = this.forms.control(this.store.$user()?.timezone ?? 'UTC');
  private readonly zonesTrigger = viewChild.required(MatAutocompleteTrigger);
  /** The server's zones, by their current names, each with its older names, which some browsers still use. */
  private readonly zones = rxResource({ stream: () => this.api.auth.timezones() });
  protected readonly $timezoneQuery = signal('');
  protected readonly $timezones = computed(() => {
    const query = searchable(this.$timezoneQuery());
    const now = new Date();
    return (this.zones.value() ?? [])
      .filter(({ name, aliases }) => [name, ...aliases].some((zone) => zone.toLowerCase().includes(query)))
      .slice(0, 50)
      .map(({ name }) => ({ zone: name, label: zoneWithOffset(name, now) }));
  });
  /** The field shows the saved zone with its offset; what the user types stays as typed. */
  protected readonly zoneLabel = zoneLabel;

  protected readonly password = this.forms.group({
    current: ['', Validators.required],
    new: ['', newPasswordValidators],
  });
  protected readonly $wrongPassword = signal(false);

  protected async saveTimezone(timezone: string): Promise<void> {
    try {
      this.store.set(await firstValueFrom(this.api.auth.updateMe(timezone)));
    } catch {
      this.notify(this.translate('app.errors.unknown'));
      return;
    } finally {
      // The autocomplete closes, and resets the field, before the server answers.
      this.resetTimezone();
    }
    this.notify(this.translate('app.profile.timezone.saved'));
  }

  /** Enter without a highlighted zone saves the typed one when it names a zone exactly, else puts the saved one back. */
  protected commitTypedTimezone(): void {
    const trigger = this.zonesTrigger();
    if (trigger.activeOption) return;
    const typed = searchable(this.timezone.value);
    const zone = this.zones
      .value()
      ?.find(({ name, aliases }) => [name, ...aliases].some((candidate) => candidate.toLowerCase() === typed))?.name;
    trigger.closePanel();
    if (zone && zone !== this.store.$user()?.timezone) void this.saveTimezone(zone);
    else this.resetTimezone();
  }

  /** The panel closes when nothing matches what is typed: the text stays while the field has the focus. */
  protected timezonePanelClosed(field: HTMLInputElement): void {
    if (field.ownerDocument.activeElement !== field) this.resetTimezone();
  }

  /** Leaving the field with text that is no zone puts the saved one back; the open panel handles a tapped option. */
  protected timezoneBlurred(): void {
    if (!this.zonesTrigger().panelOpen) this.resetTimezone();
  }

  protected resetTimezone(): void {
    this.timezone.setValue(this.store.$user()?.timezone ?? 'UTC');
    this.$timezoneQuery.set('');
  }

  protected async changePassword(): Promise<void> {
    if (this.password.invalid) return;
    this.$wrongPassword.set(false);
    const { current, new: next } = this.password.getRawValue();
    try {
      await firstValueFrom(this.api.auth.changePassword(current, next));
    } catch (error: unknown) {
      if (error instanceof HttpErrorResponse && error.status === 400) this.$wrongPassword.set(true);
      else this.notify(this.translate('app.errors.unknown'));
      return;
    }
    this.password.reset();
    this.notify(this.translate('app.profile.password.changed'));
  }

  /** The app starts again on the login page, so nothing of this user stays in memory for the next one. */
  protected async logout(everywhere: boolean): Promise<void> {
    // A signed-out device stops receiving the user's notifications.
    await this.push.disable();
    try {
      await (everywhere ? this.store.logoutEverywhere() : this.store.logout());
    } catch {
      // The session is already over on the server: the user is signed out either way.
    }
    this.store.restartAt(appRoutes.login());
  }
}
