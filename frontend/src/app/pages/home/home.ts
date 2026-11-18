import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { catchError, map, of } from 'rxjs';
import { ApiService } from '../../core/api/api.service';
import { injectTranslator } from '../../core/i18n';

type ServerStatus = 'checking' | 'online' | 'degraded' | 'offline';

/** Placeholder home page: shows that the app reaches its server. */
@Component({
  selector: 'app-home',
  templateUrl: './home.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class Home {
  protected readonly translate = injectTranslator('app');

  protected readonly $status = toSignal(
    inject(ApiService)
      .health.get()
      .pipe(
        map((): ServerStatus => 'online'),
        // Only MinTrack's own 503 says it is degraded; a proxy's 503 means the server cannot be reached.
        catchError((error: unknown) => of<ServerStatus>(isDatabaseDown(error) ? 'degraded' : 'offline')),
      ),
    { initialValue: 'checking' satisfies ServerStatus },
  );
}

function isDatabaseDown(error: unknown): boolean {
  if (!(error instanceof HttpErrorResponse) || error.status !== 503) return false;
  const body = error.error as Partial<Model.Http.HealthResponse> | null;
  return body?.status === 'degraded';
}
