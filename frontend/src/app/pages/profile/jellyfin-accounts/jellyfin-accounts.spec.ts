import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { loadProfileTexts } from '../../../core/i18n';
import { SYNC_POLL_MS } from '../../../core/jellyfin/jellyfin.store';
import { JellyfinAccounts, QUICK_CONNECT_POLL_MS } from './jellyfin-accounts';

const ACCOUNTS = '/api/jellyfin/accounts';
const SERVER = 'https://jellyfin.example.com';

function account(changes: Partial<Model.Http.JellyfinAccount> = {}): Model.Http.JellyfinAccount {
  return {
    id: 'a1',
    server_url: SERVER,
    username: 'bob',
    last_sync_at: '2026-11-18T10:00:00Z',
    last_success_at: '2026-11-18T10:00:00Z',
    last_sync_status: 'ok',
    last_sync_imported: 12,
    last_sync_skipped: 0,
    ...changes,
  };
}

describe('JellyfinAccounts', () => {
  beforeAll(() => loadProfileTexts());
  let fixture: ComponentFixture<JellyfinAccounts>;
  let http: HttpTestingController;
  let snackBar: { open: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    snackBar = { open: vi.fn() };
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: MatSnackBar, useValue: snackBar }],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  async function render(accounts: Model.Http.JellyfinAccount[]): Promise<HTMLElement> {
    fixture = TestBed.createComponent(JellyfinAccounts);
    http.expectOne(ACCOUNTS).flush(accounts);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function text(element: HTMLElement, testId: string): string {
    return element.querySelector(`[data-testid="${testId}"]`)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  }

  function button(element: HTMLElement, label: string): HTMLButtonElement {
    return [...element.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)!;
  }

  async function fill(element: HTMLElement, values: string[]): Promise<void> {
    element.querySelectorAll('[data-testid="jellyfin-link"] input').forEach((input, index) => {
      (input as HTMLInputElement).value = values[index]!;
      input.dispatchEvent(new Event('input'));
    });
    await fixture.whenStable();
  }

  async function submit(element: HTMLElement): Promise<void> {
    element.querySelector<HTMLButtonElement>('[data-testid="jellyfin-link"] button[type="submit"]')!.click();
    await fixture.whenStable();
  }

  it('follows a sync asked for until the account line shows how it went', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    const element = await render([account()]);

    button(element, 'Sync now').click();
    http.expectOne(`${ACCOUNTS}/a1/sync`).flush(null);
    vi.advanceTimersByTime(SYNC_POLL_MS);
    http.expectOne(ACCOUNTS).flush([account()]);
    vi.advanceTimersByTime(SYNC_POLL_MS);
    http.expectOne(ACCOUNTS).flush([account({ last_sync_at: '2026-11-18T11:00:00Z', last_sync_imported: 3 })]);
    await fixture.whenStable();

    expect(text(element, 'jellyfin-last-sync')).toMatch(/: 3 new plays$/);
    vi.advanceTimersByTime(SYNC_POLL_MS);
    http.expectNone(ACCOUNTS);
  });

  it('says when no account is linked', async () => {
    const element = await render([]);

    expect(text(element, 'jellyfin-empty')).toContain('No Jellyfin account linked');
  });

  it.each<[string, Partial<Model.Http.JellyfinAccount>, RegExp]>([
    ['how the last sync went', {}, /^Last sync .+: 12 new plays$/],
    ['a single play in the singular', { last_sync_imported: 1 }, /: 1 new play$/],
    ['how many played items were not recognized', { last_sync_skipped: 3 }, /12 new plays · 3 not recognized/],
    [
      'to link again when Jellyfin revoked the token, with the last successful sync',
      { last_sync_status: 'unauthorized' },
      /link the account again\.\s*Last successful sync .+/,
    ],
    [
      'a waiting state before the first sync',
      { last_sync_at: null, last_sync_status: null },
      /^Waiting for the first sync…$/,
    ],
  ])('says %s', async (_, changes, line) => {
    const element = await render([account(changes)]);

    expect(text(element, 'jellyfin-last-sync')).toMatch(line);
  });

  it('links with Quick Connect: shows the code, waits for its approval, then lists the account', async () => {
    // RxJS schedules its timers with setInterval; Angular's rendering keeps the real setTimeout.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    const element = await render([]);

    await fill(element, [SERVER]);
    await submit(element);
    http.expectOne('/api/jellyfin/quick-connect').flush({ code: '123456', secret: 's3cret' });
    await fixture.whenStable();
    expect(text(element, 'quick-connect-code')).toBe('123456');
    expect(element.querySelector('input[type="password"]')).toBeNull();

    vi.advanceTimersByTime(QUICK_CONNECT_POLL_MS);
    const pending = http.expectOne('/api/jellyfin/quick-connect/state');
    expect(pending.request.body).toEqual({ server_url: SERVER, secret: 's3cret' });
    pending.flush({ approved: false });
    vi.advanceTimersByTime(QUICK_CONNECT_POLL_MS);
    http.expectOne('/api/jellyfin/quick-connect/state').flush({ approved: true });
    const link = http.expectOne({ method: 'POST', url: `${ACCOUNTS}/quick-connect` });
    expect(link.request.body).toEqual({ server_url: SERVER, secret: 's3cret' });
    link.flush(account({ last_sync_at: null, last_sync_status: null }));
    await fixture.whenStable();

    expect(element.querySelectorAll('[data-testid="jellyfin-account"]')).toHaveLength(1);
    expect(element.querySelector('[data-testid="quick-connect"]')).toBeNull();
    expect(snackBar.open).toHaveBeenCalledWith('Jellyfin account linked', undefined, { duration: 4000 });
  });

  it('falls back to the password when the server has Quick Connect turned off', async () => {
    const element = await render([]);

    await fill(element, [SERVER]);
    await submit(element);
    http
      .expectOne('/api/jellyfin/quick-connect')
      .flush({ detail: 'jellyfin_quick_connect_disabled' }, { status: 400, statusText: 'Bad Request' });
    await fixture.whenStable();

    expect(element.querySelector('[role="alert"]')?.textContent).toContain('Quick Connect is turned off');
    await fill(element, [SERVER, 'bob', 'secret']);
    await submit(element);
    const request = http.expectOne({ method: 'POST', url: ACCOUNTS });
    expect(request.request.body).toEqual({ server_url: SERVER, username: 'bob', password: 'secret' });
    request.flush(account());
    await fixture.whenStable();

    expect(element.querySelectorAll('[data-testid="jellyfin-account"]')).toHaveLength(1);
  });

  it('explains why linking failed, and forgets it once the address changes', async () => {
    const element = await render([]);

    await fill(element, ['http://192.168.1.10:8096']);
    await submit(element);
    http
      .expectOne('/api/jellyfin/quick-connect')
      .flush({ detail: 'jellyfin_unreachable' }, { status: 502, statusText: 'Bad Gateway' });
    await fixture.whenStable();
    expect(element.querySelector('[role="alert"]')?.textContent).toContain('Cannot reach this server');

    await fill(element, ['http://192.168.1.11:8096']);

    expect(element.querySelector('[role="alert"]')).toBeNull();
  });

  it('does not send an address that is not http or https', async () => {
    const element = await render([]);

    await fill(element, ['jellyfin.local']);
    await submit(element);

    http.expectNone('/api/jellyfin/quick-connect');
  });

  it('links with a password when asked to', async () => {
    const element = await render([]);

    button(element, 'Use my password instead').click();
    await fixture.whenStable();
    await fill(element, [SERVER, 'bob', 'secret']);
    await submit(element);

    http.expectOne({ method: 'POST', url: ACCOUNTS }).flush(account());
  });

  it('removes an unlinked account at once and puts it back when the server refuses', async () => {
    const element = await render([account()]);

    button(element, 'Unlink').click();
    await fixture.whenStable();
    expect(element.querySelectorAll('[data-testid="jellyfin-account"]')).toHaveLength(0);

    http.expectOne({ method: 'DELETE', url: `${ACCOUNTS}/a1` }).flush(null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    expect(element.querySelectorAll('[data-testid="jellyfin-account"]')).toHaveLength(1);
  });

  it('starts a sync', async () => {
    const element = await render([account()]);

    button(element, 'Sync now').click();

    http.expectOne({ method: 'POST', url: `${ACCOUNTS}/a1/sync` }).flush(null, { status: 202, statusText: 'Accepted' });
  });
});
