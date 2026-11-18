import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { NavigationError } from '@angular/router';
import { SwUpdate, VersionEvent } from '@angular/service-worker';
import { Subject } from 'rxjs';
import { PAGE_LOCATION } from '../auth/auth.store';
import { promptForUpdates, reloadOnMissingChunk } from './update-prompt';

function fakeRef() {
  const dismissed = new Subject<{ dismissedByAction: boolean }>();
  return { onAction: () => new Subject<void>(), afterDismissed: () => dismissed, dismissed };
}

describe('promptForUpdates', () => {
  let versionUpdates: Subject<VersionEvent>;
  let unrecoverable: Subject<{ type: 'UNRECOVERABLE_STATE'; reason: string }>;
  const refs: ReturnType<typeof fakeRef>[] = [];
  const open = vi.fn(() => {
    refs.push(fakeRef());
    return refs.at(-1)!;
  });
  const snackBar = { open, _openedSnackBarRef: null as ReturnType<typeof fakeRef> | null };
  const checkForUpdate = vi.fn(() => Promise.resolve(false));
  const assign = vi.fn();

  beforeEach(() => {
    versionUpdates = new Subject();
    unrecoverable = new Subject();
    refs.length = 0;
    open.mockClear();
    checkForUpdate.mockClear();
    assign.mockClear();
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        { provide: SwUpdate, useValue: { isEnabled: true, versionUpdates, unrecoverable, checkForUpdate } },
        { provide: MatSnackBar, useValue: snackBar },
        { provide: PAGE_LOCATION, useValue: { assign } },
      ],
    });
    TestBed.runInInjectionContext(promptForUpdates);
  });

  afterEach(() => vi.restoreAllMocks());

  it('offers the reload again once another message that replaced it is gone', async () => {
    versionUpdates.next({ type: 'VERSION_READY', currentVersion: { hash: 'a' }, latestVersion: { hash: 'b' } });
    await vi.waitFor(() => expect(open).toHaveBeenCalledOnce());

    const other = fakeRef();
    snackBar._openedSnackBarRef = other;
    refs[0].dismissed.next({ dismissedByAction: false });
    expect(open).toHaveBeenCalledOnce();
    other.dismissed.next({ dismissedByAction: false });

    expect(open).toHaveBeenCalledTimes(2);
    expect(open).toHaveBeenLastCalledWith('A new version of MinTrack is available', 'Reload');
  });

  it('does not reload for a missing page while offline, where the reload would fail', () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);

    TestBed.runInInjectionContext(() =>
      reloadOnMissingChunk(new NavigationError(1, '/discover', new TypeError('Importing a module script failed'))),
    );

    expect(assign).not.toHaveBeenCalled();
  });

  it('offers a reload when a new version is ready', async () => {
    versionUpdates.next({ type: 'VERSION_DETECTED', version: { hash: 'b' } });
    versionUpdates.next({ type: 'VERSION_READY', currentVersion: { hash: 'a' }, latestVersion: { hash: 'b' } });

    await vi.waitFor(() => expect(open).toHaveBeenCalledOnce());
    expect(open).toHaveBeenCalledWith('A new version of MinTrack is available', 'Reload');
  });

  it('offers a reload when the cached version is broken', async () => {
    unrecoverable.next({ type: 'UNRECOVERABLE_STATE', reason: 'missing chunk' });

    await vi.waitFor(() => expect(open).toHaveBeenCalledWith('MinTrack needs to reload to keep working', 'Reload'));
  });

  it('looks for a new version when the app comes back to the screen', () => {
    document.dispatchEvent(new Event('visibilitychange'));

    expect(checkForUpdate).toHaveBeenCalledOnce();
  });

  it('loads the app again, once, when a page’s code is gone from the server', () => {
    const missing = new NavigationError(1, '/discover', new TypeError('Failed to fetch dynamically imported module'));

    TestBed.runInInjectionContext(() => reloadOnMissingChunk(missing));
    TestBed.runInInjectionContext(() => reloadOnMissingChunk(missing));
    TestBed.runInInjectionContext(() => reloadOnMissingChunk(new NavigationError(2, '/profile', new Error('boom'))));

    expect(assign).toHaveBeenCalledExactlyOnceWith('/discover');
  });
});
