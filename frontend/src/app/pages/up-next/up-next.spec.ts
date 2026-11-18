import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import UpNext from './up-next';

describe('UpNext', () => {
  beforeEach(() =>
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] }),
  );

  async function render(respond: (http: HttpTestingController) => void): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(UpNext);
    // The resource sends its request from an effect.
    TestBed.tick();
    respond(TestBed.inject(HttpTestingController));
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('lists the next episode of each show in the order the server gives', async () => {
    const episodes = ['Andor', 'Severance'].map((show_title, index) => ({
      episode_id: String(index),
      tmdb_id: index + 1,
      show_title,
      poster_path: null,
      season_number: 1,
      episode_number: 3,
      title: 'Next one',
      airstamp: null,
      day: '2026-11-11',
    }));
    const page = await render((http) =>
      http.expectOne('/api/up-next').flush({ episodes } satisfies Model.Http.UpNextResponse),
    );

    expect([...page.querySelectorAll('[data-testid="episode"] h3')].map((title) => title.textContent?.trim())).toEqual([
      'Andor',
      'Severance',
    ]);
  });

  it('says when there is nothing to watch next', async () => {
    const page = await render((http) => http.expectOne('/api/up-next').flush({ episodes: [] }));

    expect(page.querySelector('[data-testid="empty"]')?.textContent?.trim()).toBe(
      'Nothing to watch next. The next episode of each show you are watching appears here.',
    );
  });

  it('says when the list cannot be loaded', async () => {
    const page = await render((http) =>
      http.expectOne('/api/up-next').flush('boom', { status: 500, statusText: 'Server Error' }),
    );

    expect(page.querySelector('[role="alert"]')?.textContent?.trim()).toBe('Cannot load your next episodes.');
  });
});
