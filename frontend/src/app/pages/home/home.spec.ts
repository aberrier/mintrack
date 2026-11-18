import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import Home from './home';

describe('Home', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }));

  async function statusAfter(respond: (http: HttpTestingController) => void): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Home);
    respond(TestBed.inject(HttpTestingController));
    await fixture.whenStable();
    return (fixture.nativeElement as HTMLElement).querySelector('[data-testid="server-status"]')!;
  }

  it('says the server is online when the health check passes', async () => {
    const status = await statusAfter((http) => http.expectOne('/api/health').flush({ status: 'ok', database: 'ok' }));

    expect(status.textContent?.trim()).toBe('Online');
  });

  it('says the database is unavailable when the server answers 503', async () => {
    const status = await statusAfter((http) =>
      http
        .expectOne('/api/health')
        .flush({ status: 'degraded', database: 'unavailable' }, { status: 503, statusText: 'Service Unavailable' }),
    );

    expect(status.textContent?.trim()).toBe('Online, but the database is unavailable');
  });

  it('says the server cannot be reached when a proxy answers 503 in its place', async () => {
    const status = await statusAfter((http) =>
      http.expectOne('/api/health').flush('no available server', { status: 503, statusText: 'Service Unavailable' }),
    );

    expect(status.textContent?.trim()).toBe('Cannot reach the server');
  });

  it('says the server cannot be reached when the request fails', async () => {
    const status = await statusAfter((http) =>
      http.expectOne('/api/health').error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' }),
    );

    expect(status.textContent?.trim()).toBe('Cannot reach the server');
  });
});
