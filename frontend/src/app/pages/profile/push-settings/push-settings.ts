import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { MatSlideToggle, MatSlideToggleChange } from '@angular/material/slide-toggle';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../../app.paths';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { PushState, PushStore } from '../../../core/push/push.store';

/** One short line per state, read with the switch; while loading, the line of a switch that is off. */
const STATUS: Record<PushState, TranslationPath<'app'>> = {
  loading: 'app.push.status.off',
  off: 'app.push.status.off',
  on: 'app.push.status.on',
  install: 'app.push.status.install',
  unsupported: 'app.push.status.unsupported',
  unconfigured: 'app.push.status.unconfigured',
  blocked: 'app.push.status.blocked',
};

/** The notifications switch for this device with its state, its test button and the link to the guide. */
@Component({
  selector: 'app-push-settings',
  imports: [MatSlideToggle, MatButton, RouterLink],
  templateUrl: './push-settings.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PushSettings {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  protected readonly store = inject(PushStore);

  protected readonly $canToggle = computed(
    () => !this.store.$busy() && (this.store.$state() === 'on' || this.store.$state() === 'off'),
  );
  protected readonly $status = computed(() => STATUS[this.store.$state()]);

  protected async toggle(event: MatSlideToggleChange): Promise<void> {
    await (event.checked ? this.store.enable() : this.store.disable());
    // The switch moved on tap; it shows what really happened (a refused permission leaves it off).
    event.source.checked = this.store.$state() === 'on';
  }
}
