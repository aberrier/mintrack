import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { SwUpdate, VersionEvent } from '@angular/service-worker';
import { Subject } from 'rxjs';
import { promptForUpdates } from './update-prompt';

describe('promptForUpdates', () => {
  let versionUpdates: Subject<VersionEvent>;
  let unrecoverable: Subject<{ type: 'UNRECOVERABLE_STATE'; reason: string }>;
  const open = vi.fn(() => ({ onAction: () => new Subject<void>() }));

  beforeEach(() => {
    versionUpdates = new Subject();
    unrecoverable = new Subject();
    open.mockClear();
    TestBed.configureTestingModule({
      providers: [
        { provide: SwUpdate, useValue: { isEnabled: true, versionUpdates, unrecoverable } },
        { provide: MatSnackBar, useValue: { open } },
      ],
    });
    TestBed.runInInjectionContext(promptForUpdates);
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
});
