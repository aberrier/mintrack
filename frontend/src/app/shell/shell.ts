import { CdkScrollable } from '@angular/cdk/scrolling';
import { ChangeDetectionStrategy, Component, inject, Signal } from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { isActive, Router, RouterLink, RouterOutlet } from '@angular/router';
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
 * The app frame: a scrolling content area and, once signed in, a bottom navigation, both clear of the notch and the
 * gesture bar.
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
  protected readonly $user = inject(AuthStore).$user;
  private readonly router = inject(Router);

  protected readonly navItems: NavItem[] = [
    this.item(appRoutes.watchList(), appRoutes.episodes(), 'live_tv', 'live_tv_fill', 'app.nav.episodes'),
    this.item(appRoutes.discover(), appRoutes.discover(), 'explore', 'explore_fill', 'app.nav.discover'),
    this.item(appRoutes.profile(), appRoutes.profile(), 'person', 'person_fill', 'app.nav.profile'),
  ];

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
