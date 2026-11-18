import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { MatButtonToggle, MatButtonToggleGroup } from '@angular/material/button-toggle';
import { MatProgressBar } from '@angular/material/progress-bar';
import { injectTranslator } from '../../../core/i18n';
import { ImportsStore } from '../../../core/imports/imports.store';

/** Upload a Yamtrack or TV Time export, then follow the import until its report. */
@Component({
  selector: 'app-import-card',
  imports: [MatButton, MatButtonToggleGroup, MatButtonToggle, MatProgressBar],
  providers: [ImportsStore],
  templateUrl: './import-card.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ImportCard {
  protected readonly translate = injectTranslator('app');
  protected readonly store = inject(ImportsStore);
  protected readonly $source = signal<Model.Http.ImportSource>('yamtrack');

  protected readonly $job = this.store.$latest;
  protected readonly $active = this.store.$active;
  protected readonly $unlisted = computed(() => {
    const report = this.$job()?.report;
    return report ? report.unmatched_count - report.unmatched.length : 0;
  });

  protected upload(input: HTMLInputElement): void {
    const file = input.files?.[0];
    input.value = '';
    if (file) this.store.upload(this.$source(), file);
  }
}
