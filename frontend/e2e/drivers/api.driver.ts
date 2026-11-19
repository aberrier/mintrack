import { APIResponse, expect, Page, request } from '@playwright/test';

/** User agents of messaging apps' link previews, which fetch a shared link before the person opens it. */
const PREVIEW_AGENTS = ['WhatsApp/2.24.1 A', 'facebookexternalhit/1.1', 'TelegramBot (like TwitterBot)', 'Signal'];

/** Fetch a link as link previews do: without cookies or JavaScript, with GET and HEAD, several times. */
export async function previewLink(link: string): Promise<void> {
  for (const userAgent of PREVIEW_AGENTS) {
    const crawler = await request.newContext({ userAgent });
    for (const method of ['GET', 'HEAD']) {
      const response = await crawler.fetch(link, { method });
      expect(response.status()).toBe(200);
    }
    await crawler.dispose();
  }
}

/**
 * The API back-channel, for given state the scenarios do not exercise. Sends what the app itself sends: the page's
 * session cookie and, on unsafe methods, the XSRF header.
 */
export class ApiDriver {
  constructor(private readonly page: Page) {}

  /** Use a password link as the password page does; the session cookies land in the page's browser context. */
  async usePasswordLink(link: string, password: string): Promise<void> {
    const timezone = await this.page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
    const response = await this.page.request.post('/api/auth/password-link/use', {
      data: { token: new URL(link).hash.slice(1), password, timezone },
    });
    if (!response.ok()) throw new Error(`Password link refused: ${response.status()}`);
  }

  async findShow(title: string): Promise<number> {
    const response = await this.page.request.get('/api/search', { params: { query: title, type: 'tv' } });
    const results = (await response.json()) as { tmdb_id: number; media_type: string; title: string }[];
    return results.find((result) => result.media_type === 'tv' && result.title === title)!.tmdb_id;
  }

  async findMovie(title: string): Promise<number> {
    const response = await this.page.request.get('/api/search', { params: { query: title, type: 'movie' } });
    const results = (await response.json()) as { tmdb_id: number; title: string }[];
    return results.find((result) => result.title === title)!.tmdb_id;
  }

  loadShow(tmdbId: number): Promise<APIResponse> {
    return this.page.request.get(`/api/shows/${tmdbId}`);
  }

  /** Add a movie found by its title, to watch later. */
  async addMovie(title: string): Promise<void> {
    const tmdbId = await this.findMovie(title);
    expect((await this.page.request.get(`/api/movies/${tmdbId}`)).ok(), `Loading movie "${title}"`).toBe(true);
    const added = await this.page.request.put(`/api/movies/${tmdbId}/tracking`, {
      data: { watched: false },
      headers: await this.xsrf(),
    });
    expect(added.ok(), `Adding movie "${title}"`).toBe(true);
  }

  async addShow(tmdbId: number): Promise<APIResponse> {
    return this.page.request.put(`/api/shows/${tmdbId}/tracking`, {
      data: { status: 'watching' },
      headers: await this.xsrf(),
    });
  }

  /** Mark episodes, given as [season, episode], of a show found by its title; returns the show's TMDB id. */
  async markWatched(title: string, episodes: [number, number][]): Promise<number> {
    const tmdbId = await this.findShow(title);
    const response = await this.loadShow(tmdbId);
    expect(response.ok(), `Loading show "${title}"`).toBe(true);
    // The show lists its seasons; each season's episodes come from its own endpoint.
    const ids: string[] = [];
    for (const season of new Set(episodes.map(([s]) => s))) {
      const loaded = await this.page.request.get(`/api/shows/${tmdbId}/seasons/${season}`);
      expect(loaded.ok(), `Loading season ${season} of "${title}"`).toBe(true);
      const { episodes: listed } = (await loaded.json()) as {
        episodes: { id: string; season_number: number; episode_number: number }[];
      };
      for (const episode of listed)
        if (episodes.some(([s, e]) => episode.season_number === s && episode.episode_number === e))
          ids.push(episode.id);
    }
    const marked = await this.page.request.post(`/api/shows/${tmdbId}/watched`, {
      data: { episode_ids: ids, watched: true },
      headers: await this.xsrf(),
    });
    expect(marked.ok(), `Marking episodes of "${title}"`).toBe(true);
    return tmdbId;
  }

  /** The signed-in user's time zone, in which the app shows days. */
  async timeZone(): Promise<string> {
    const response = await this.page.request.get('/api/auth/me');
    return ((await response.json()) as { timezone: string }).timezone;
  }

  private async xsrf(): Promise<Record<string, string>> {
    const cookie = (await this.page.context().cookies()).find((c) => c.name === 'XSRF-TOKEN');
    return { 'X-XSRF-TOKEN': cookie?.value ?? '' };
  }
}
