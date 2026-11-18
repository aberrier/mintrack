import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatAutocomplete, MatAutocompleteTrigger, MatOption } from '@angular/material/autocomplete';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatInput } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { appRoutes } from '../../app.paths';
import { ApiService } from '../../core/api/api.service';
import { AuthStore } from '../../core/auth/auth.store';
import { injectTranslator } from '../../core/i18n';
import { PushStore } from '../../core/push/push.store';
import { libraryKey, TrackingStore } from '../../core/tracking/tracking.store';
import { MediaTile } from '../../shared/media-tile';
import { Skeleton } from '../../shared/skeleton';
import { ApiTokens } from './api-tokens/api-tokens';
import { ImportCard } from './import-card/import-card';
import { JellyfinAccounts } from './jellyfin-accounts/jellyfin-accounts';
import { PushSettings } from './push-settings/push-settings';

const ROW_LENGTH = 20;
const TIMEZONES = ['UTC', ...Intl.supportedValuesOf('timeZone').filter((zone) => zone !== 'UTC')];

@Component({
  selector: 'app-profile',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatFormField,
    MatLabel,
    MatHint,
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
  ],
  templateUrl: './profile.html',
  styles: `
    .avatar {
      display: grid;
      flex: none;
      place-items: center;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
      font: var(--mat-sys-title-large);
      font-weight: 600;
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
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly forms = inject(NonNullableFormBuilder);

  protected readonly $user = this.store.$user;
  protected readonly $isAdmin = this.store.$isAdmin;
  protected readonly $initial = computed(() => this.$user()?.username.charAt(0) ?? '');

  /** The most recently watched first, as many as a row shows before See all. */
  protected readonly rowLength = ROW_LENGTH;
  protected readonly rows = (['tv', 'movie'] as const).map((type) => {
    // The cached row renders at once; the fresh one then replaces it.
    this.tracking
      .loadLibrary({ mediaType: type })
      .pipe(takeUntilDestroyed())
      .subscribe({ error: () => undefined });
    const key = libraryKey({ mediaType: type });
    return {
      type,
      title: this.translate(type === 'tv' ? 'app.library.shows' : 'app.library.movies'),
      empty: this.translate(type === 'tv' ? 'app.profile.noShows' : 'app.profile.noMovies'),
      $items: computed(() => this.tracking.library()[key]),
    };
  });

  protected link(item: Model.Http.LibraryItem): string {
    return item.media_type === 'tv' ? appRoutes.show(item.tmdb_id) : appRoutes.movie(item.tmdb_id);
  }

  protected readonly timezone = this.forms.control(this.store.$user()?.timezone ?? 'UTC');
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
      this.showUnknownError();
      return;
    } finally {
      // The autocomplete closes, and resets the field, before the server answers.
      this.resetTimezone();
    }
    this.snackBar.open(this.translate('app.profile.timezone.saved'), undefined, { duration: 3000 });
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
      else this.showUnknownError();
      return;
    }
    this.password.reset();
    this.snackBar.open(this.translate('app.profile.password.changed'), undefined, { duration: 4000 });
  }

  protected async logout(everywhere: boolean): Promise<void> {
    // A signed-out device stops receiving the user's notifications.
    await this.push.disable();
    try {
      await (everywhere ? this.store.logoutEverywhere() : this.store.logout());
    } catch {
      // The session is already over on the server: the user is signed out either way.
    }
    await this.router.navigateByUrl(appRoutes.login());
  }

  private showUnknownError(): void {
    this.snackBar.open(this.translate('app.errors.unknown'), undefined, { duration: 4000 });
  }
}
