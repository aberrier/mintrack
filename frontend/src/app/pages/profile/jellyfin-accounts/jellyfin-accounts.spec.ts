import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { JellyfinAccounts } from './jellyfin-accounts';

const ACCOUNTS = '/api/jellyfin/accounts';

function account(changes: Partial<Model.Http.JellyfinAccount> = {}): Model.Http.JellyfinAccount {
  return {
    id: 'a1',
    server_url: 'https://jellyfin.example.com',
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
  let fixture: ComponentFixture<JellyfinAccounts>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function render(accounts: Model.Http.JellyfinAccount[]): Promise<HTMLElement> {
    fixture = TestBed.createComponent(JellyfinAccounts);
    http.expectOne(ACCOUNTS).flush(accounts);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function text(element: HTMLElement, testId: string): string {
    return element.querySelector(`[data-testid="${testId}"]`)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  }

  async function fillAndSubmit(element: HTMLElement, values: [string, string, string]): Promise<void> {
    element.querySelectorAll('input').forEach((input, index) => {
      input.value = values[index]!;
      input.dispatchEvent(new Event('input'));
    });
    element.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();
    await fixture.whenStable();
  }

  it('says when no account is linked', async () => {
    const element = await render([]);

    expect(text(element, 'jellyfin-empty')).toContain('No Jellyfin account linked');
  });

  it('shows how the last sync went', async () => {
    const element = await render([account()]);

    expect(text(element, 'jellyfin-last-sync')).toMatch(/^Last sync .+: 12 new plays$/);
  });

  it('says how many played items were not recognised', async () => {
    const element = await render([account({ last_sync_skipped: 3 })]);

    expect(text(element, 'jellyfin-last-sync')).toMatch(/12 new plays · 3 not recognised/);
  });

  it('asks to link again when Jellyfin revoked the token, with the last successful sync', async () => {
    const element = await render([account({ last_sync_status: 'unauthorized' })]);

    expect(text(element, 'jellyfin-last-sync')).toMatch(/link the account again\.\s*Last successful sync .+/);
  });

  it('shows a waiting state before the first sync', async () => {
    const element = await render([account({ last_sync_at: null, last_sync_status: null })]);

    expect(text(element, 'jellyfin-last-sync')).toBe('Waiting for the first sync…');
  });

  it('links an account and lists it', async () => {
    const element = await render([]);

    await fillAndSubmit(element, ['https://jellyfin.example.com', 'bob', 'secret']);
    const request = http.expectOne({ method: 'POST', url: ACCOUNTS });
    expect(request.request.body).toEqual({
      server_url: 'https://jellyfin.example.com',
      username: 'bob',
      password: 'secret',
    });
    request.flush(account({ last_sync_at: null, last_sync_status: null }));
    await fixture.whenStable();

    expect(element.querySelectorAll('[data-testid="jellyfin-account"]')).toHaveLength(1);
    expect(element.querySelector<HTMLInputElement>('input')!.value).toBe('');
    expect(element.querySelector('mat-error')).toBeNull();
  });

  it('explains why linking failed', async () => {
    const element = await render([]);

    await fillAndSubmit(element, ['http://192.168.1.10:8096', 'bob', 'secret']);
    http
      .expectOne({ method: 'POST', url: ACCOUNTS })
      .flush({ detail: 'jellyfin_unreachable' }, { status: 502, statusText: 'Bad Gateway' });
    await fixture.whenStable();

    expect(element.querySelector('[role="alert"]')?.textContent).toContain('Cannot reach this server');
  });

  it('does not send an address that is not http or https', async () => {
    const element = await render([]);

    await fillAndSubmit(element, ['jellyfin.local', 'bob', 'secret']);

    http.expectNone({ method: 'POST', url: ACCOUNTS });
  });

  it('removes an unlinked account at once and puts it back when the server refuses', async () => {
    const element = await render([account()]);
    const unlink = [...element.querySelectorAll('button')].find((button) => button.textContent?.includes('Unlink'))!;

    unlink.click();
    await fixture.whenStable();
    expect(element.querySelectorAll('[data-testid="jellyfin-account"]')).toHaveLength(0);

    http.expectOne({ method: 'DELETE', url: `${ACCOUNTS}/a1` }).flush(null, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    expect(element.querySelectorAll('[data-testid="jellyfin-account"]')).toHaveLength(1);
  });

  it('starts a sync', async () => {
    const element = await render([account()]);
    const sync = [...element.querySelectorAll('button')].find((button) => button.textContent?.includes('Sync now'))!;

    sync.click();

    http.expectOne({ method: 'POST', url: `${ACCOUNTS}/a1/sync` }).flush(null, { status: 202, statusText: 'Accepted' });
  });
});
