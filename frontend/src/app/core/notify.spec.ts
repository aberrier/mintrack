import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideRouter, Router } from '@angular/router';
import { Subject } from 'rxjs';
import { injectNotify } from './notify';

@Component({ template: '' })
class Page {}

describe('injectNotify', () => {
  let dismiss: ReturnType<typeof vi.fn>;
  let open: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    dismiss = vi.fn();
    open = vi.fn(() => ({ dismiss, afterDismissed: () => new Subject() }));
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'a', component: Page },
          { path: 'b', component: Page },
        ]),
        { provide: MatSnackBar, useValue: { open } },
      ],
    });
    await TestBed.inject(Router).navigateByUrl('/a');
  });

  it('lets a message go after a few seconds', () => {
    TestBed.runInInjectionContext(injectNotify)('Saved');

    expect(open).toHaveBeenCalledWith('Saved', undefined, { duration: 4000 });
  });

  it('keeps a message with an action longer, until the user moves to another page', async () => {
    const router = TestBed.inject(Router);
    TestBed.runInInjectionContext(injectNotify)('Moved to Watch later', 'Undo');
    expect(open).toHaveBeenCalledWith('Moved to Watch later', 'Undo', { duration: 10_000 });

    await router.navigateByUrl('/a?view=grid');
    expect(dismiss).not.toHaveBeenCalled();
    await router.navigateByUrl('/b');

    expect(dismiss).toHaveBeenCalledOnce();
  });
});
