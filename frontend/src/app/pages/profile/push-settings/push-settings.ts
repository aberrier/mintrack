import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { MatSlideToggle, MatSlideToggleChange } from '@angular/material/slide-toggle';
import { injectTranslator } from '../../../core/i18n';
import { PushStore } from '../../../core/push/push.store';

/** The notifications switch for this device, its test button and why it may be unavailable. */
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

  protected async toggle(event: MatSlideToggleChange): Promise<void> {
    await (event.checked ? this.store.enable() : this.store.disable());
    // The switch moved on tap; it shows what really happened (a refused permission leaves it off).
    event.source.checked = this.store.$state() === 'on';
  }
}
