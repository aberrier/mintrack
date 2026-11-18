import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatAutocomplete, MatAutocompleteTrigger, MatOption } from '@angular/material/autocomplete';
import { MatButton } from '@angular/material/button';
import { MatError, MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { ApiService } from '../../core/api/api.service';
import { AuthStore } from '../../core/auth/auth.store';
import { injectTranslator, TranslationPath } from '../../core/i18n';
import { injectNotify } from '../../core/notify';
import { PushStore } from '../../core/push/push.store';
import { libraryKey, LibraryQuery, TrackingStore } from '../../core/tracking/tracking.store';
import { LoadError } from '../../shared/load-error';
import { MediaTile } from '../../shared/media-tile';
import { Skeleton } from '../../shared/skeleton';
import { ApiTokens } from './api-tokens/api-tokens';
import { ImportCard } from './import-card/import-card';
import { JellyfinAccounts } from './jellyfin-accounts/jellyfin-accounts';
import { PushSettings } from './push-settings/push-settings';

const ROW_LENGTH = 20;
const TIMEZONES = ['UTC', ...Intl.supportedValuesOf('timeZone').filter((zone) => zone !== 'UTC')];

/**
 * The user's own place: their shows, movies and shows set aside to watch later, each row opening the whole
 * collection, then the settings in groups (account, notifications, integrations, import history) and logging out.
 */
@Component({
  selector: 'app-profile',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatFormField,
    MatLabel,
    MatHint,
    MatError,
    MatInput,
    MatButton,
    MatAutocomplete,
    MatAutocompleteTrigger,
    MatOption,
    PushSettings,
    JellyfinAccounts,
    ImportCard,
    ApiTokens,
    MediaTile,
    Skeleton,
    LoadError,
  ],
  templateUrl: './profile.html',
  styles: `
    .avatar {
      display: grid;
      flex: none;
      place-items: center;
      width: 56px;
      height: 56px;
      border-radius: var(--mat-sys-corner-full);
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
      font: var(--mat-sys-title-large);
      font-weight: 600;
      text-transform: uppercase;
    }
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
export default class Profile {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  private readonly api = inject(ApiService);
  private readonly store = inject(AuthStore);
  private readonly tracking = inject(TrackingStore);
  private readonly push = inject(PushStore);
  private readonly notify = injectNotify();
  private readonly forms = inject(NonNullableFormBuilder);

  protected readonly $user = this.store.$user;
  protected readonly $initial = computed(() => this.$user()?.username.charAt(0) ?? '');

  /** The most recently watched first, as many as a row shows before See all. */
  protected readonly rowLength = ROW_LENGTH;
  protected readonly rows = [
    this.row('shows', { mediaType: 'tv' }, 'app.common.shows', 'app.profile.noShows'),
    this.row('movies', { mediaType: 'movie' }, 'app.common.movies', 'app.profile.noMovies'),
    // Shows set aside from the watch list, one tap away; the row hides while there is none.
    this.row('watch-later', { mediaType: 'tv', status: 'watch_later' }, 'app.status.watch_later', null),
  ];

  protected readonly timezone = this.forms.control(this.store.$user()?.timezone ?? 'UTC');
  private readonly zonesTrigger = viewChild.required(MatAutocompleteTrigger);
  protected readonly $timezoneQuery = signal('');
  protected readonly $timezones = computed(() => {
    const query = this.$timezoneQuery().toLowerCase().replaceAll(' ', '_');
    return TIMEZONES.filter((zone) => zone.toLowerCase().includes(query)).slice(0, 50);
  });

  protected readonly password = this.forms.group({
    current: ['', Validators.required],
    new: ['', [Validators.required, Validators.minLength(15), Validators.maxLength(128)]],
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
    const typed = this.timezone.value.trim().toLowerCase().replaceAll(' ', '_');
    const zone = TIMEZONES.find((candidate) => candidate.toLowerCase() === typed);
    trigger.closePanel();
    if (zone && zone !== this.store.$user()?.timezone) void this.saveTimezone(zone);
    else this.resetTimezone();
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

  private row(id: string, query: LibraryQuery, title: TranslationPath<'app'>, empty: TranslationPath<'app'> | null) {
    const $failed = signal(false);
    const destroyRef = inject(DestroyRef);
    // The cached row renders at once; the fresh one then replaces it.
    const load = () => {
      $failed.set(false);
      this.tracking
        .loadLibrary(query)
        .pipe(takeUntilDestroyed(destroyRef))
        .subscribe({ error: () => $failed.set(true) });
    };
    load();
    const key = libraryKey(query);
    return {
      id,
      title: this.translate(title),
      empty: empty && this.translate(empty),
      seeAll: { type: query.mediaType, progress: query.status ?? null },
      $items: computed(() => this.tracking.library()[key]),
      $failed: $failed.asReadonly(),
      retry: load,
    };
  }
}
