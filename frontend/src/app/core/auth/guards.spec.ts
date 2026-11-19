import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AuthStore, PAGE_LOCATION } from './auth.store';
import { adminGuard, safeNext, signedInGuard, signedOutGuard, signedOutOn401 } from './guards';

const alice: Model.Http.User = { id: '1', username: 'alice', is_admin: false, timezone: 'UTC' };

describe('auth guards', () => {
  let location: { assign: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    location = { assign: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([signedOutOn401])),
        provideHttpClientTesting(),
        { provide: PAGE_LOCATION, useValue: location },
      ],
    });
  });

  function run(guard: typeof signedInGuard, url: string) {
    return TestBed.runInInjectionContext(() =>
      guard({} as ActivatedRouteSnapshot, { url } as RouterStateSnapshot),
    ) as Promise<unknown>;
  }

  it('sends signed-out users to the login page with the page they asked for', async () => {
    TestBed.inject(AuthStore).clear();

    const result = await run(signedInGuard, '/profile?tab=1');

    expect(TestBed.inject(Router).serializeUrl(result as never)).toBe('/login?next=%2Fprofile%3Ftab%3D1');
  });

  it('lets signed-in users through and keeps non-admins out of admin pages', async () => {
    TestBed.inject(AuthStore).set(alice);

    expect(await run(signedInGuard, '/profile')).toBe(true);
    expect(TestBed.inject(Router).serializeUrl((await run(adminGuard, '/admin/users')) as never)).toBe(
      '/episodes/watch-list',
    );
  });

  it('keeps signed-in users away from the login page', async () => {
    TestBed.inject(AuthStore).set(alice);

    expect(TestBed.inject(Router).serializeUrl((await run(signedOutGuard, '/login')) as never)).toBe(
      '/episodes/watch-list',
    );
  });

  it('keeps pages closed and says the server cannot be reached when it does not answer', async () => {
    const result = run(signedInGuard, '/profile');
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/me')
      .flush(null, { status: 504, statusText: 'Gateway Timeout' });

    expect(await result).toBe(false);
    expect(TestBed.inject(AuthStore).$failure()).toBe('unreachable');
    expect(TestBed.inject(AuthStore).$blockedUrl()).toBe('/profile');
  });

  it('tells a server error apart from a server out of reach', async () => {
    const result = run(signedInGuard, '/profile');
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/me')
      .flush(null, { status: 500, statusText: 'Internal Server Error' });

    expect(await result).toBe(false);
    expect(TestBed.inject(AuthStore).$failure()).toBe('error');
  });

  it('starts the app afresh on the login page when the session ends, once for many requests', async () => {
    const store = TestBed.inject(AuthStore);
    store.set(alice);

    const http = TestBed.inject(HttpClient);
    const requests = [http.get('/api/library'), http.get('/api/history')].map((r) => firstValueFrom(r));
    for (const request of TestBed.inject(HttpTestingController).match(() => true))
      request.flush(null, { status: 401, statusText: 'Unauthorized' });

    for (const request of requests) await expect(request).rejects.toBeTruthy();
    expect(store.$user()).toBeNull();
    expect(location.assign).toHaveBeenCalledExactlyOnceWith('/login?next=%2F');
  });

  it('leaves a wrong password to the login page', async () => {
    const request = firstValueFrom(TestBed.inject(HttpClient).post('/api/auth/login', {}));
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/login')
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    await expect(request).rejects.toBeTruthy();
    expect(location.assign).not.toHaveBeenCalled();
  });

  it('follows only paths inside the app after login', () => {
    expect(safeNext('/profile')).toBe('/profile');
    expect(safeNext('//evil.example')).toBe('/episodes/watch-list');
    expect(safeNext('/\\evil.example')).toBe('/episodes/watch-list');
    expect(safeNext('https://evil.example')).toBe('/episodes/watch-list');
    expect(safeNext(null)).toBe('/episodes/watch-list');
  });
});
