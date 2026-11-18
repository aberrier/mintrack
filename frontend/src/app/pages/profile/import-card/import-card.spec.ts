import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ImportsStore } from '../../../core/imports/imports.store';
import { ImportCard } from './import-card';

const job = (changes: Partial<Model.Http.ImportJob>): Model.Http.ImportJob => ({
  id: 'job-1',
  source: 'yamtrack',
  status: 'pending',
  filename: 'export.csv',
  total: 0,
  processed: 0,
  report: null,
  created_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  ...changes,
});

const nextTask = () => new Promise((resolve) => setTimeout(resolve));
const storeOf = (fixture: ComponentFixture<ImportCard>) => fixture.debugElement.injector.get(ImportsStore);

describe('ImportCard', () => {
  let http: HttpTestingController;
  let settle: () => Promise<void>;
  let store: () => ImportsStore;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
  });

  async function render(latest: Model.Http.ImportJob | null): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(ImportCard);
    store = () => storeOf(fixture);
    settle = async () => {
      await nextTask();
      await fixture.whenStable();
    };
    await nextTask();
    http.expectOne('/api/imports/latest').flush(latest);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the report of the latest import with the unmatched titles and their reason', async () => {
    const card = await render(
      job({
        status: 'done',
        report: {
          imported: 12,
          already_present: 3,
          unmatched_count: 502,
          unmatched: [
            { title: 'Some Game', reason: 'unsupported' },
            { title: 'Lost Show', reason: 'not_found' },
          ],
        },
      }),
    );

    const report = [...card.querySelectorAll('[data-testid="import-report"] > *')].map((cell) =>
      cell.textContent?.trim(),
    );
    expect(report).toEqual(['Added', '12', 'Already there', '3', 'Not matched', '502']);
    const items = [...card.querySelectorAll('li')].map((item) => item.textContent?.trim());
    expect(items).toEqual([
      'Some Game: not a movie or show on TMDB',
      'Lost Show: not found on TMDB',
      '500 more not listed',
    ]);
  });

  it('keeps following imports after a failed read', async () => {
    const fixture = TestBed.createComponent(ImportCard);
    await nextTask();
    http.expectOne('/api/imports/latest').error(new ProgressEvent('error'));

    storeOf(fixture).upload('tvtime', new File(['x'], 'export.zip'));
    http.expectOne('/api/imports').flush(job({ status: 'pending' }));
    await nextTask();
    http
      .expectOne('/api/imports/latest')
      .flush(job({ status: 'done', report: { imported: 1, already_present: 0, unmatched_count: 0, unmatched: [] } }));
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="import-report"]')).not.toBeNull();
  });

  it('shows why the server refused the file', async () => {
    const card = await render(null);

    store().upload('yamtrack', new File(['x'], 'other.csv'));
    http
      .expectOne('/api/imports')
      .flush({ detail: 'This is not a Yamtrack CSV export.' }, { status: 422, statusText: 'Unprocessable Content' });
    await settle();

    expect(card.querySelector('[role="alert"]')?.textContent?.trim()).toBe('This is not a Yamtrack CSV export.');
  });
});
