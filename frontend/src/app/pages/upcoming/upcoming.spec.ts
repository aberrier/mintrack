import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { dayIn, nextDay } from './air-time';
import Upcoming from './upcoming';

const TIME_ZONE = 'Pacific/Auckland';

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
  beforeEach(() =>
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] }),
  );

  async function render(
    response: Model.Http.UpcomingResponse | string,
    options?: { status: number; statusText: string },
  ): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Upcoming);
    // The resource sends its request from an effect.
    TestBed.tick();
    TestBed.inject(HttpTestingController).expectOne('/api/upcoming').flush(response, options);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function text(element: Element): string {
    return element.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  }

  it('groups episodes under Today, Tomorrow and dates of the user time zone, with local times', async () => {
    const today = dayIn(TIME_ZONE);
    const tomorrow = nextDay(today);
    const airstamp = '2026-11-20T08:00:00Z';
    const page = await render({
      time_zone: TIME_ZONE,
      new: [],
      days: [
        { day: today, episodes: [episode({ show_title: 'Tonight', airstamp, day: today })] },
        { day: tomorrow, episodes: [episode({ show_title: 'Soon', season_number: 2, episode_number: 10 })] },
        { day: '2099-01-02', episodes: [episode({ show_title: 'Later', title: '' })] },
      ],
    });

    const days = [...page.querySelectorAll('[data-testid="day"]')];
    expect(days.map((day) => text(day.querySelector('h2')!))).toEqual(['Today', 'Tomorrow', 'Friday, January 2']);
    const localTime = new Intl.DateTimeFormat(undefined, { timeStyle: 'short', timeZone: TIME_ZONE }).format(
      new Date(airstamp),
    );
    expect(text(days[0].querySelector('[data-testid="episode-detail"]')!)).toBe(localTime);
    expect(text(days[1].querySelector('[data-testid="episode"] p')!)).toBe('S02E10 · Pilot');
    expect(days[1].querySelector('[data-testid="episode-detail"]')).toBeNull();
    expect(text(days[2].querySelector('[data-testid="episode"] p')!)).toBe('S01E01');
    expect(page.querySelector('[data-testid="new"]')).toBeNull();
  });

  it('lists new episodes first, with their air day', async () => {
    const page = await render({
      time_zone: TIME_ZONE,
      new: [episode({ show_title: 'Missed', day: '2026-11-13' })],
      days: [],
    });

    const section = page.querySelector('[data-testid="new"]')!;
    expect(text(section.querySelector('h2')!)).toBe('New episodes');
    expect(text(section.querySelector('[data-testid="episode-detail"]')!)).toBe('Fri, Nov 13');
    expect(page.querySelector('[data-testid="empty"]')).toBeNull();
  });

  it('says when nothing airs soon', async () => {
    const page = await render({ time_zone: TIME_ZONE, new: [], days: [] });

    expect(text(page.querySelector('[data-testid="empty"]')!)).toBe(
      'Nothing airs in the next four weeks for the shows you follow.',
    );
  });

  it('says when the episodes cannot be loaded', async () => {
    const page = await render('boom', { status: 500, statusText: 'Server Error' });

    expect(text(page.querySelector('[role="alert"]')!)).toBe('Cannot load the upcoming episodes.');
    expect(page.querySelector('[data-testid="day"]')).toBeNull();
  });
});
