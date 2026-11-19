import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButton } from '@angular/material/button';
import { appRoutes } from '../../../app.paths';
import { injectCopy } from '../../../core/copy';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { BackButton } from '../../../shared/back-button';

/** The path of the MCP server, outside /api, on the origin serving the app. */
const MCP_PATH = '/mcp';
const TOKEN = 'YOUR_TOKEN';

/** The MCP server's tools, as an assistant sees them. */
const TOOLS: { name: string; description: TranslationPath<'app'> }[] = [
  { name: 'search_media', description: 'app.mcpHelp.tools.searchMedia' },
  { name: 'get_show_progress', description: 'app.mcpHelp.tools.getShowProgress' },
  { name: 'mark_episode_watched', description: 'app.mcpHelp.tools.markEpisodeWatched' },
  { name: 'unmark_episode_watched', description: 'app.mcpHelp.tools.unmarkEpisodeWatched' },
  { name: 'mark_movie_watched', description: 'app.mcpHelp.tools.markMovieWatched' },
  { name: 'unmark_movie_watched', description: 'app.mcpHelp.tools.unmarkMovieWatched' },
  { name: 'set_show_status', description: 'app.mcpHelp.tools.setShowStatus' },
  { name: 'list_upcoming', description: 'app.mcpHelp.tools.listUpcoming' },
  { name: 'list_up_next', description: 'app.mcpHelp.tools.listUpNext' },
];

/** How to connect an AI assistant to MinTrack's MCP server: what MCP is, the token, the address, the tools. */
@Component({
  selector: 'app-mcp-help',
  imports: [BackButton, MatButton],
  templateUrl: './mcp-help.html',
  styles: `
    h2 {
      font: var(--mat-sys-title-medium);
    }
    p {
      color: var(--mat-sys-on-surface-variant);
      font: var(--mat-sys-body-large);
    }
    /* Code wraps rather than scrolls, so a phone shows all of it. */
    pre {
      padding: 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border-radius: var(--mat-sys-corner-small);
      background: var(--mat-sys-surface-container-high);
      font:
        400 14px / 20px ui-monospace,
        monospace;
    }
    code {
      font-family: ui-monospace, monospace;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class McpHelp {
  protected readonly translate = injectTranslator('app');
  protected readonly appRoutes = appRoutes;
  protected readonly tools = TOOLS;
  private readonly copyText = injectCopy();

  protected readonly url = `${inject(DOCUMENT).location.origin}${MCP_PATH}`;
  protected readonly json = JSON.stringify(
    { mcpServers: { mintrack: { type: 'http', url: this.url, headers: { Authorization: `Bearer ${TOKEN}` } } } },
    null,
    2,
  );
  protected readonly command = `claude mcp add --transport http mintrack ${this.url} --header "Authorization: Bearer ${TOKEN}"`;

  protected copy(text: string): void {
    this.copyText(text, 'app.mcpHelp.copied');
  }
}
