import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { Confetti } from '../../shared/confetti';
import Show from './show';

function episode(season: number, number: number, airDate: string | null): Model.Http.Episode {
  return {
    id: `${season}x${number}`,
    season_number: season,
    episode_number: number,
    title: '',
    air_date: airDate,
    airstamp: null,
  };
}

function show(watched: string[], tmdbStatus = 'Ended'): Model.Http.Show {
  return {
    tmdb_id: 7,
    title: 'Show',
    overview: '',
    poster_path: null,
    release_date: null,
    tmdb_status: tmdbStatus,
    backdrop_path: null,
    network: 'Channel',
    runtime: null,
    seasons: [
      { season_number: 1, title: 'Season 1', episodes: [episode(1, 1, '2020-01-01'), episode(1, 2, '2020-01-08')] },
      {
        season_number: 2,
        title: 'Season 2',
        episodes: [episode(2, 1, '2020-02-01'), episode(2, 2, '2999-01-01'), episode(2, 3, null)],
      },
      { season_number: 0, title: 'Specials', episodes: [episode(0, 1, '2020-01-02')] },
    ],
    tracking: { status: 'watching', watched: Object.fromEntries(watched.map((id) => [id, '2020-03-01T00:00:00Z'])) },
  };
}

describe('Show', () => {
  let fixture: ComponentFixture<Show>;
  let http: HttpTestingController;
  let confetti: { launch: ReturnType<typeof vi.fn> };
  let dialog: { open: ReturnType<typeof vi.fn> };

  async function open(loaded: Model.Http.Show): Promise<HTMLElement> {
    confetti = { launch: vi.fn() };
    dialog = { open: vi.fn(() => ({ afterClosed: () => of(true) })) };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Confetti, useValue: confetti },
        { provide: MatDialog, useValue: dialog },
        { provide: MatSnackBar, useValue: { open: vi.fn() } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Show);
    fixture.componentRef.setInput('tmdbId', 7);
    await fixture.whenStable();
    http.expectOne('/api/shows/7').flush(loaded);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function button(page: HTMLElement, name: string): HTMLButtonElement | undefined {
    return [...page.querySelectorAll('button')].find(
      (b) => (b.getAttribute('aria-label') ?? b.textContent)?.trim() === name,
    );
  }

  function sentIds(watched: boolean): string[] {
    const request = http.expectOne('/api/shows/7/watched');
    expect(request.request.body.watched).toBe(watched);
    return request.request.body.episode_ids as string[];
  }

  it('marks the aired, dated episodes of a season in one tap, never the unaired or undated ones', async () => {
    const page = await open(show([], 'Returning Series'));

    button(page, 'Mark Season 2 watched')!.click();

    expect(sentIds(true)).toEqual(['2x1']);
    await fixture.whenStable();
    expect(page.textContent).toContain('1/1');
  });

  it('asks before unmarking a fully watched season, then unmarks it', async () => {
    const page = await open(show(['1x1', '1x2'], 'Returning Series'));
    const check = button(page, 'Mark Season 1 watched')!;
    expect(check.getAttribute('aria-pressed')).toBe('true');

    check.click();

    expect(dialog.open).toHaveBeenCalledOnce();
    expect(sentIds(false)).toEqual(['1x1', '1x2']);
  });

  it('renders a season’s episodes only once it is open', async () => {
    const page = await open(show([]));
    expect(button(page, 'Season 1, episode 1')).toBeUndefined();

    [...page.querySelectorAll<HTMLButtonElement>('button[aria-expanded]')][0].click();
    await fixture.whenStable();

    expect(button(page, 'Season 1, episode 1')).toBeDefined();
  });

  it('throws confetti when the last aired episode of an ended show is marked', async () => {
    const ended = show(['1x1', '1x2']);
    // Nothing left to air: the undated episode does not count.
    ended.seasons[1].episodes.splice(1, 1);
    const page = await open(ended);

    button(page, 'Mark Season 2 watched')!.click();

    expect(confetti.launch).toHaveBeenCalledOnce();
    sentIds(true);
  });

  it('throws no confetti for a show still running', async () => {
    const page = await open(show(['1x1', '1x2'], 'Returning Series'));

    button(page, 'Mark Season 2 watched')!.click();

    expect(confetti.launch).not.toHaveBeenCalled();
    sentIds(true);
  });
});
