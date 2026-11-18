import { CdkScrollable } from '@angular/cdk/scrolling';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { appRoutes } from '../app.paths';
import { AuthStore } from '../core/auth/auth.store';
import { injectTranslator, TranslationPath } from '../core/i18n';
import { IconName } from '../core/icons/icons';

interface NavItem {
  route: string;
  icon: IconName;
  label: TranslationPath<'app'>;
}

/**
 * The app frame: a scrolling content area and, once signed in, a bottom navigation, both clear of the notch and the
 * gesture bar.
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatIcon, CdkScrollable],
  templateUrl: './shell.html',
  styleUrl: './shell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shell {
  protected readonly translate = injectTranslator('app');
  protected readonly $user = inject(AuthStore).$user;

  protected readonly navItems: NavItem[] = [
    { route: appRoutes.home(), icon: 'home', label: 'app.nav.home' },
    { route: appRoutes.profile(), icon: 'person', label: 'app.nav.profile' },
  ];
}
