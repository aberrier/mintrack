import { HttpErrorResponse } from '@angular/common/http';
import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, EMPTY, finalize, startWith, Subject, switchMap, takeWhile, timer } from 'rxjs';
import { ApiService } from '../api/api.service';

/** Milliseconds between two reads of a pending or running import. */
export const POLL_INTERVAL = 2000;

/** The user's latest import, read again until it ends; provided per page, so each visit reads it afresh. */
@Injectable()
export class ImportsStore {
  private readonly api = inject(ApiService);
  private readonly poll$ = new Subject<void>();

  private readonly $job = signal<Model.Http.ImportJob | null | undefined>(undefined);
  private readonly $sending = signal(false);
  private readonly $error = signal<string | null>(null);

  /** `undefined` until loaded, `null` when the user never imported. */
  readonly $latest = this.$job.asReadonly();
  readonly $active = computed(() => isActive(this.$job() ?? null));
  readonly $uploading = this.$sending.asReadonly();
  /** The server's reason for refusing the last upload, `''` when it gave none. */
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
        error: (error: unknown) => this.$error.set(serverReason(error)),
      });
  }
}

function isActive(job: Model.Http.ImportJob | null): boolean {
  return job?.status === 'pending' || job?.status === 'running';
}

function serverReason(error: unknown): string {
  const detail = error instanceof HttpErrorResponse ? (error.error as { detail?: unknown } | null)?.detail : undefined;
  return typeof detail === 'string' ? detail : '';
}
