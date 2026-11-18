import { APIResponse, Page } from '@playwright/test';

/**
 * The API back-channel, for given state the scenarios do not exercise. Sends what the app itself sends: the page's
 * session cookie and, on unsafe methods, the XSRF header.
 */
export class ApiDriver {
  constructor(private readonly page: Page) {}

  async findShow(title: string): Promise<number> {
    const response = await this.page.request.get('/api/search', { params: { query: title } });
    const results = (await response.json()) as { tmdb_id: number; media_type: string; title: string }[];
    return results.find((result) => result.media_type === 'tv' && result.title === title)!.tmdb_id;
  }

  loadShow(tmdbId: number): Promise<APIResponse> {
    return this.page.request.get(`/api/shows/${tmdbId}`);
  }

  async addShow(tmdbId: number): Promise<APIResponse> {
    return this.page.request.put(`/api/shows/${tmdbId}/tracking`, {
      data: { stopped: false },
      headers: await this.xsrf(),
    });
  }

  private async xsrf(): Promise<Record<string, string>> {
    const cookie = (await this.page.context().cookies()).find((c) => c.name === 'XSRF-TOKEN');
    return { 'X-XSRF-TOKEN': cookie?.value ?? '' };
  }
}
