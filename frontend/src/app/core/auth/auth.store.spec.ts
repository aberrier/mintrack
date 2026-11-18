import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AuthStore } from './auth.store';

const alice: Model.Http.User = { id: '1', username: 'alice', is_admin: false, timezone: 'UTC' };

describe('AuthStore', () => {
  let store: AuthStore;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    store = TestBed.inject(AuthStore);
    http = TestBed.inject(HttpTestingController);
  });

  it('asks the server once for the current user', async () => {
    const first = store.load();
    const second = store.load();
    http.expectOne('/api/auth/me').flush(alice);

    expect(await first).toEqual(alice);
    expect(await second).toEqual(alice);
    expect(await store.load()).toEqual(alice);
    http.verify();
  });

  it('is signed out when the server answers 401', async () => {
    const user = store.load();
    http.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(await user).toBeNull();
    expect(store.$user()).toBeNull();
  });

  it('forgets the user after logging out', async () => {
    store.set(alice);

    const done = store.logout();
    http.expectOne('/api/auth/logout').flush(null);
    await done;

    expect(store.$user()).toBeNull();
  });
});
