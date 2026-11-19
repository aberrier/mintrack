import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { MatButtonToggle, MatButtonToggleGroup } from '@angular/material/button-toggle';
import { MatIcon } from '@angular/material/icon';
import { MatProgressBar } from '@angular/material/progress-bar';
import { AuthStore } from '../../../core/auth/auth.store';
import { formatDateTime } from '../../../core/dates';
import { injectTranslator } from '../../../core/i18n';
import { ImportsStore } from '../../../core/imports/imports.store';

/**
 * The import of a Yamtrack or TV Time export: the previous import first (when, from where, its report), with Import
 * another file; otherwise, or then, the choice of source and file, and the import followed until its report.
 */
@Component({
  selector: 'app-import-card',
  imports: [MatButton, MatButtonToggleGroup, MatButtonToggle, MatProgressBar, MatIcon],
  providers: [ImportsStore],
  templateUrl: './import-card.html',
  styles: `
    /* What was not imported, folded under its count until asked for. */
    .warnings summary {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 48px;
      cursor: pointer;
      font: var(--mat-sys-label-large);
      list-style: none;
    }
    .warnings summary::-webkit-details-marker {
      display: none;
    }
    .chevron {
      transition: transform var(--duration-short) var(--ease-standard);
    }
    .warnings[open] .chevron {
      transform: rotate(180deg);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ImportCard {
  protected readonly translate = injectTranslator('app');
  protected readonly store = inject(ImportsStore);
  private readonly timeZone = inject(AuthStore).$timeZone;
  protected readonly $source = signal<Model.Http.ImportSource>('yamtrack');
  /** The user asked to import another file after the previous one. */
  protected readonly $another = signal(false);

  protected readonly $job = this.store.$latest;
  protected readonly $active = this.store.$active;
  /** The form shows when nothing was imported yet, or once asked for. */
  protected readonly $showForm = computed(() => this.$job() === null || this.$another() || !!this.store.$uploadError());
  protected readonly $unlisted = computed(() => {
    const report = this.$job()?.report;
    return report ? report.unmatched_count - report.unmatched.length : 0;
  });

  protected heading(job: Model.Http.ImportJob): string {
    return this.translate('app.profile.imports.last', {
      source: this.translate(`app.profile.imports.${job.source}`),
      date: formatDateTime(job.finished_at ?? job.created_at, this.timeZone()),
    });
  }

  protected upload(input: HTMLInputElement): void {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.store.upload(this.$source(), file);
    this.$another.set(false);
  }
}
