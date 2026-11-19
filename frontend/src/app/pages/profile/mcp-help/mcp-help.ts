import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { MatButton } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../../app.paths';
import { ApiService } from '../../../core/api/api.service';
import { injectCopy } from '../../../core/copy';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { BackButton } from '../../../shared/back-button';
import { LoadError } from '../../../shared/load-error';

const TOKEN = 'YOUR_TOKEN';

/** The MCP server's tools, as an assistant sees them; a server test checks this list against the server's. */
const TOOLS: { name: string; description: TranslationPath<'app'> }[] = [
  { name: 'search_media', description: 'app.mcpHelp.tools.searchMedia' },
  { name: 'get_show_progress', description: 'app.mcpHelp.tools.getShowProgress' },
  { name: 'mark_episode_watched', description: 'app.mcpHelp.tools.markEpisodeWatched' },
  { name: 'unmark_episode_watched', description: 'app.mcpHelp.tools.unmarkEpisodeWatched' },
  { name: 'mark_movie_watched', description: 'app.mcpHelp.tools.markMovieWatched' },
  { name: 'unmark_movie_watched', description: 'app.mcpHelp.tools.unmarkMovieWatched' },
  { name: 'set_show_status', description: 'app.mcpHelp.tools.setShowStatus' },
  { name: 'list_upcoming', description: 'app.mcpHelp.tools.listUpcoming' },
  { name: 'list_watch_list', description: 'app.mcpHelp.tools.listWatchList' },
];

/**
 * How to connect an AI assistant to MinTrack's MCP server: what MCP is, the token, the address (on the server's public
 * URL), the tools.
 */
@Component({
  selector: 'app-mcp-help',
  imports: [BackButton, MatButton, RouterLink, LoadError],
  templateUrl: './mcp-help.html',
  styleUrl: '../help-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class McpHelp {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  protected readonly tools = TOOLS;
  private readonly api = inject(ApiService);
  private readonly copyText = injectCopy();

  protected readonly about = rxResource({ stream: () => this.api.about() });
  /** The address and the two ways to configure it, once the server gave its public URL. */
  protected readonly $setup = computed(() => {
    if (!this.about.hasValue()) return null;
    const url = this.about.value().mcp_url;
    return {
      url,
      json: JSON.stringify(
        { mcpServers: { mintrack: { type: 'http', url, headers: { Authorization: `Bearer ${TOKEN}` } } } },
        null,
        2,
      ),
      command: `claude mcp add --transport http mintrack ${url} --header "Authorization: Bearer ${TOKEN}"`,
    };
  });

  protected copy(text: string, copied: TranslationPath<'app'>): void {
    this.copyText(text, copied);
  }
}
