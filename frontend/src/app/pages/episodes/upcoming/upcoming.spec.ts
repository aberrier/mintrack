import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import Upcoming from './upcoming';

const TIME_ZONE = 'Pacific/Auckland';
// Thursday 26 November 2026, 1 AM in Auckland.
const NOW = new Date('2026-11-25T12:00:00Z');

function episode(overrides: Partial<Model.Http.UpcomingEpisode>): Model.Http.UpcomingEpisode {
  return {
    episode_id: crypto.randomUUID(),
    tmdb_id: 1,
    show_title: 'Show',
    poster_path: '/show.jpg',
    season_number: 1,
    episode_number: 1,
    title: 'Pilot',
    airstamp: null,
    day: null,
    ...overrides,
  };
}

describe('Upcoming', () => {
  let fixture: ComponentFixture<Upcoming>;
  let http: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => vi.useRealTimers());

  async function render(
    response: Model.Http.UpcomingResponse | string,
    options?: { status: number; statusText: string },
  ): Promise<HTMLElement> {
    fixture = TestBed.createComponent(Upcoming);
    // The resource sends its request from an effect.
    TestBed.tick();
    http.expectOne('/api/upcoming').flush(response, options);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function text(element: Element): string {
    return element.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  }

  it('groups episodes under Today, Tomorrow, the weekdays until Sunday, then dates, with local times', async () => {
    const airstamp = '2026-11-26T08:00:00Z';
    const page = await render({
      time_zone: TIME_ZONE,
      days: [
        { day: '2026-11-26', episodes: [episode({ show_title: 'Tonight', airstamp, day: '2026-11-26' })] },
        { day: '2026-11-27', episodes: [episode({ show_title: 'Soon', season_number: 2, episode_number: 10 })] },
        { day: '2026-11-29', episodes: [episode({ show_title: 'Sunday' })] },
        { day: '2026-12-06', episodes: [episode({ show_title: 'Later', title: '' })] },
      ],
    });

    const days = [...page.querySelectorAll('[data-testid="day"]')];
    expect(days.map((day) => text(day.querySelector('h2')!))).toEqual(['Today', 'Tomorrow', 'Sunday', '6 December']);
    expect(text(days[0].querySelector('[data-testid="episode-detail"]')!)).toBe('21:00');
    expect(text(days[1].querySelector('[data-testid="episode-code"]')!)).toBe('S02 | E10');
    expect(text(days[1].querySelector('[data-testid="episode-title"]')!)).toBe('Pilot');
    expect(days[1].querySelector('[data-testid="episode-detail"]')).toBeNull();
    expect(days[3].querySelector('[data-testid="episode-title"]')).toBeNull();
  });

  it('names the month where a new one starts, with the year when it is another one', async () => {
    const page = await render({
      time_zone: TIME_ZONE,
      days: [
        { day: '2026-11-28', episodes: [episode({})] },
        { day: '2026-12-02', episodes: [episode({})] },
        { day: '2026-12-20', episodes: [episode({})] },
        { day: '2027-01-02', episodes: [episode({})] },
      ],
    });

    const headings = [...page.querySelectorAll('[data-testid="month"], [data-testid="day"] h2')].map(text);
    expect(headings).toEqual(['Saturday', 'December', '2 December', '20 December', 'January 2027', '2 January 2027']);
  });

  it('says when nothing airs soon', async () => {
    const page = await render({ time_zone: TIME_ZONE, days: [] });

    expect(text(page.querySelector('[data-testid="empty"]')!)).toBe(
      'Nothing airs in the next four weeks for the shows you follow.',
    );
  });

  it('says when the episodes cannot be loaded, and tries again on request', async () => {
    const page = await render('boom', { status: 500, statusText: 'Server Error' });

    expect(text(page.querySelector('[role="alert"]')!)).toBe('Cannot load the upcoming episodes.');
    expect(page.querySelector('[data-testid="day"]')).toBeNull();

    [...page.querySelectorAll('button')].find((button) => text(button) === 'Try again')!.click();
    TestBed.tick();
    http
      .expectOne('/api/upcoming')
      .flush({ time_zone: TIME_ZONE, days: [{ day: '2026-11-26', episodes: [episode({})] }] });
    await fixture.whenStable();

    expect(page.querySelectorAll('[data-testid="day"]')).toHaveLength(1);
  });
});
