import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { MatSlideToggle, MatSlideToggleChange } from '@angular/material/slide-toggle';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { PushState, PushStore } from '../../../core/push/push.store';

const HINTS: Partial<Record<PushState, TranslationPath<'app'>>> = {
  install: 'app.push.hints.install',
  unsupported: 'app.push.hints.unsupported',
  unconfigured: 'app.push.hints.unconfigured',
  blocked: 'app.push.hints.blocked',
};

/** The notifications switch for this device, its test button and, read with the switch, why it may be unavailable. */
@Component({
  selector: 'app-push-settings',
  imports: [MatSlideToggle, MatButton],
  templateUrl: './push-settings.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PushSettings {
  protected readonly translate = injectTranslator('app');
  protected readonly store = inject(PushStore);

  protected readonly $canToggle = computed(
    () => !this.store.$busy() && (this.store.$state() === 'on' || this.store.$state() === 'off'),
  );
  protected readonly $hint = computed(() => HINTS[this.store.$state()] ?? null);

  protected async toggle(event: MatSlideToggleChange): Promise<void> {
    await (event.checked ? this.store.enable() : this.store.disable());
    // The switch moved on tap; it shows what really happened (a refused permission leaves it off).
    event.source.checked = this.store.$state() === 'on';
  }
}
