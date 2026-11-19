import { HttpErrorResponse } from '@angular/common/http';
import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, EMPTY, finalize, startWith, Subject, switchMap, takeWhile, timer } from 'rxjs';
import { ApiService } from '../api/api.service';
import { TranslationPath } from '../i18n';

/** Milliseconds between two reads of a pending or running import. */
const POLL_INTERVAL = 2000;

/** Why the server refused an upload, by HTTP status. */
const UPLOAD_ERRORS: Record<number, TranslationPath<'app'>> = {
  409: 'app.profile.imports.errors.inProgress',
  413: 'app.profile.imports.errors.tooLarge',
  422: 'app.profile.imports.errors.unreadable',
};

/** The user's latest import, read again until it ends; provided per page, so each visit reads it afresh. */
@Injectable()
export class ImportsStore {
  private readonly api = inject(ApiService);
  private readonly poll$ = new Subject<void>();

  private readonly $job = signal<Model.Http.ImportJob | null | undefined>(undefined);
  private readonly $sending = signal(false);
  private readonly $error = signal<TranslationPath<'app'> | null>(null);

  /** `undefined` until loaded, `null` when the user never imported. */
  readonly $latest = this.$job.asReadonly();
  readonly $active = computed(() => isActive(this.$job() ?? null));
  readonly $uploading = this.$sending.asReadonly();
  /** Why the last upload was refused. */
  readonly $uploadError = this.$error.asReadonly();

  constructor() {
    this.poll$
      .pipe(
        startWith(undefined),
        switchMap(() =>
          timer(0, POLL_INTERVAL).pipe(
            // A failed read skips one tick instead of ending the polling.
            switchMap(() => this.api.imports.latest().pipe(catchError(() => EMPTY))),
            takeWhile((job) => isActive(job), true),
          ),
        ),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe({ next: (job) => this.$job.set(job) });
  }

  upload(source: Model.Http.ImportSource, file: File): void {
    this.$sending.set(true);
    this.$error.set(null);
    this.api.imports
      .create(source, file)
      .pipe(finalize(() => this.$sending.set(false)))
      .subscribe({
        next: (job) => {
          this.$job.set(job);
          this.poll$.next();
        },
        error: (error: unknown) => {
          const status = error instanceof HttpErrorResponse ? error.status : 0;
          this.$error.set(UPLOAD_ERRORS[status] ?? 'app.profile.imports.errors.sendFailed');
        },
      });
  }
}

function isActive(job: Model.Http.ImportJob | null): boolean {
  return job?.status === 'pending' || job?.status === 'running';
}
