import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AuthStore } from './auth.store';
import { adminGuard, safeNext, signedInGuard, signedOutOn401 } from './guards';

const alice: Model.Http.User = { id: '1', username: 'alice', is_admin: false, timezone: 'UTC' };

describe('auth guards', () => {
  beforeEach(() =>
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withInterceptors([signedOutOn401])), provideHttpClientTesting()],
    }),
  );

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
    expect(TestBed.inject(Router).serializeUrl((await run(adminGuard, '/admin/users')) as never)).toBe('/');
  });

  it('signs out and goes to the login page when the session ends', async () => {
    const store = TestBed.inject(AuthStore);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    store.set(alice);

    const request = firstValueFrom(TestBed.inject(HttpClient).post('/api/auth/logout', null));
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/logout')
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    await expect(request).rejects.toBeTruthy();
    expect(store.$user()).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login?next=%2F');
  });

  it('leaves a wrong password to the login page', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);

    const request = firstValueFrom(TestBed.inject(HttpClient).post('/api/auth/login', {}));
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/login')
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    await expect(request).rejects.toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
  });

  it('follows only paths inside the app after login', () => {
    expect(safeNext('/profile')).toBe('/profile');
    expect(safeNext('//evil.example')).toBe('/');
    expect(safeNext('/\\evil.example')).toBe('/');
    expect(safeNext('https://evil.example')).toBe('/');
    expect(safeNext(null)).toBe('/');
  });
});
