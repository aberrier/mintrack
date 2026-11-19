import { CdkScrollable } from '@angular/cdk/scrolling';
import { ChangeDetectionStrategy, Component, computed, inject, Signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatIcon } from '@angular/material/icon';
import { isActive, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter, fromEvent } from 'rxjs';
import { appRoutes } from '../app.paths';
import { AuthStore } from '../core/auth/auth.store';
import { injectTranslator, TranslationPath } from '../core/i18n';
import { IconName } from '../core/icons/icons';
import { ScrollRestoration } from './scroll-restoration';

interface NavItem {
  /** The tab's first page. */
  route: string;
  icon: IconName;
  /** The filled icon, shown while the tab is active. */
  activeIcon: IconName;
  label: TranslationPath<'app'>;
  /** Whether the current page belongs to the tab, whatever its query, such as /discover?type=movie. */
  $active: Signal<boolean>;
}

/**
 * The app frame: a scrolling content area and, once signed in, a bottom navigation (with an Admin tab for admins),
 * both clear of the notch and the gesture bar. When the server cannot be reached before anyone is signed in, the
 * content area says so instead of staying blank.
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, MatIcon, CdkScrollable, ScrollRestoration],
  templateUrl: './shell.html',
  styleUrl: './shell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shell {
  protected readonly translate = injectTranslator('app');
  private readonly auth = inject(AuthStore);
  private readonly router = inject(Router);
  protected readonly $user = this.auth.$user;
  protected readonly $failure = computed(() => (this.auth.$user() ? null : this.auth.$failure()));

  private readonly tabs: NavItem[] = [
    this.item(appRoutes.watchList(), appRoutes.episodes(), 'live_tv', 'live_tv_fill', 'app.nav.episodes'),
    this.item(appRoutes.discover(), appRoutes.discover(), 'explore', 'explore_fill', 'app.nav.discover'),
    this.item(appRoutes.profile(), appRoutes.profile(), 'person', 'person_fill', 'app.nav.profile'),
  ];
  private readonly adminTab = this.item(
    appRoutes.admin(),
    appRoutes.admin(),
    'admin_panel_settings',
    'admin_panel_settings_fill',
    'app.nav.admin',
  );
  protected readonly $navItems = computed(() => (this.auth.$isAdmin() ? [...this.tabs, this.adminTab] : this.tabs));

  constructor() {
    // Back online, the unreachable screen asks the server again by itself.
    fromEvent(window, 'online')
      .pipe(
        filter(() => this.$failure() === 'unreachable'),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.retry());
  }

  /** Ask the server again, opening the page that could not open. */
  protected retry(): void {
    void this.router.navigateByUrl(this.auth.$blockedUrl() ?? this.router.url);
  }

  /** A tab opening `route`, active on every page under `section`. */
  private item(
    route: string,
    section: string,
    icon: IconName,
    activeIcon: IconName,
    label: TranslationPath<'app'>,
  ): NavItem {
    const $active = isActive(section, this.router, { paths: 'subset', queryParams: 'ignored' });
    return { route, icon, activeIcon, label, $active };
  }
}
