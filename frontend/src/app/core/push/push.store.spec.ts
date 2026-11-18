import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { SwPush } from '@angular/service-worker';
import { of } from 'rxjs';
import { PushStore } from './push.store';

const OTHER_KEY = 'BAUG';

/** A browser subscription made for `key` (base64url of the bytes 1, 2, 3 is AQID). */
function browserSubscription(endpoint: string, key = 'AQID'): PushSubscription {
  const bytes = Uint8Array.from(atob(key.replaceAll('-', '+').replaceAll('_', '/')), (char) => char.charCodeAt(0));
  return {
    endpoint,
    options: { applicationServerKey: bytes.buffer, userVisibleOnly: true },
    toJSON: () => ({ endpoint, keys: { p256dh: 'p', auth: 'a' } }),
    unsubscribe: vi.fn(async () => true),
  } as unknown as PushSubscription;
}

describe('PushStore', () => {
  let requestPermission: ReturnType<typeof vi.fn>;
  let swPush: {
    isEnabled: boolean;
    subscription: unknown;
    requestSubscription: ReturnType<typeof vi.fn>;
    unsubscribe: ReturnType<typeof vi.fn>;
  };
  const snackBar = { open: vi.fn() };

  function setUp(existing: PushSubscription | null, serverKey: string | null = 'AQID') {
    swPush.subscription = of(existing);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SwPush, useValue: swPush },
        { provide: MatSnackBar, useValue: snackBar },
      ],
    });
    const store = TestBed.inject(PushStore);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/push/key').flush({ public_key: serverKey });
    return { store, http };
  }

  beforeEach(() => {
    requestPermission = vi.fn(async () => 'granted');
    vi.stubGlobal('PushManager', class {});
    vi.stubGlobal('Notification', { permission: 'default', requestPermission });
    swPush = {
      isEnabled: true,
      subscription: of(null),
      requestSubscription: vi.fn(async () => browserSubscription('https://push.example/new')),
      unsubscribe: vi.fn(async () => undefined),
    };
  });

  afterEach(() => vi.unstubAllGlobals());

  it('is off until the user turns it on', async () => {
    const { store } = setUp(null);

    await vi.waitFor(() => expect(store.$state()).toBe('off'));
  });

  it('says the server is not configured when it has no key', async () => {
    const { store } = setUp(null, null);

    expect(store.$state()).toBe('unconfigured');
  });

  it('asks for permission before anything else, then registers the device', async () => {
    const { store, http } = setUp(null);
    await vi.waitFor(() => expect(store.$state()).toBe('off'));

    const enabling = store.enable();
    expect(requestPermission).toHaveBeenCalledOnce();
    await vi.waitFor(() => http.expectOne('/api/push/subscriptions').flush(null));
    await enabling;

    expect(swPush.requestSubscription).toHaveBeenCalledWith({ serverPublicKey: 'AQID' });
    expect(store.$state()).toBe('on');
  });

  it('stays off when the permission is refused', async () => {
    requestPermission.mockResolvedValue('denied');
    const { store } = setUp(null);
    await vi.waitFor(() => expect(store.$state()).toBe('off'));

    await store.enable();

    expect(swPush.requestSubscription).not.toHaveBeenCalled();
    expect(store.$state()).toBe('blocked');
  });

  it('sends the existing subscription again on start', async () => {
    const { store, http } = setUp(browserSubscription('https://push.example/old'));

    await vi.waitFor(() => {
      const request = http.expectOne('/api/push/subscriptions');
      expect(request.request.body.endpoint).toBe('https://push.example/old');
      request.flush(null);
    });
    await vi.waitFor(() => expect(store.$state()).toBe('on'));
  });

  it('replaces a subscription made for another server key', async () => {
    const old = browserSubscription('https://push.example/old', OTHER_KEY);
    const { store, http } = setUp(old);

    await vi.waitFor(() => {
      const request = http.expectOne('/api/push/subscriptions');
      expect(request.request.body.endpoint).toBe('https://push.example/new');
      request.flush(null);
    });
    expect(old.unsubscribe).toHaveBeenCalled();
    await vi.waitFor(() => expect(store.$state()).toBe('on'));
  });

  it('turns off when the server no longer knows the device', async () => {
    const { store, http } = setUp(browserSubscription('https://push.example/old'));
    await vi.waitFor(() => http.expectOne('/api/push/subscriptions').flush(null));
    await vi.waitFor(() => expect(store.$state()).toBe('on'));

    const testing = store.sendTest();
    http.expectOne('/api/push/test').flush(null, { status: 404, statusText: 'Not Found' });
    await testing;

    expect(swPush.unsubscribe).toHaveBeenCalled();
    expect(store.$state()).toBe('off');
  });

  it('asks to add the app to the Home Screen in an iPhone browser tab', () => {
    swPush.isEnabled = true;
    vi.stubGlobal('PushManager', undefined);
    delete (window as { PushManager?: unknown }).PushManager;
    Object.defineProperty(navigator, 'standalone', { value: false, configurable: true });
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: SwPush, useValue: swPush }],
    });

    expect(TestBed.inject(PushStore).$state()).toBe('install');
    delete (navigator as { standalone?: boolean }).standalone;
  });
});
