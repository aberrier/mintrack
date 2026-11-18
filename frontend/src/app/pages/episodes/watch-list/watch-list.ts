import { CdkScrollable } from '@angular/cdk/scrolling';
import {
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { Router } from '@angular/router';
import { appRoutes } from '../../../app.paths';
import { AuthStore } from '../../../core/auth/auth.store';
import { formatDate } from '../../../core/dates';
import { injectTranslator, TranslationPath } from '../../../core/i18n';
import { SetAside, WatchListStore } from '../../../core/tracking/watch-list.store';
import { CollapsedSections } from '../../../shared/collapsed-sections';
import { EmptyState } from '../../../shared/empty-state';
import { CardAction, EpisodeCard, historyCard } from '../../../shared/episode-card/episode-card';
import { LoadError } from '../../../shared/load-error';
import { PullToLoad } from '../../../shared/pull-to-load';
import { Skeleton } from '../../../shared/skeleton';
import { ViewModes } from '../../../shared/view-toggle';
import { EpisodesTabs } from '../episodes-tabs';

const SECTIONS: Record<Model.Http.WatchListSection, TranslationPath<'app'>> = {
  next: 'app.watchList.next',
  dormant: 'app.watchList.dormant',
  not_started: 'app.watchList.notStarted',
};

/**
 * The next episode of each show in progress, watched lately or not for a while, each checked in one tap. Above it,
 * the watch history loads page by page as the user scrolls up from the top, the content they look at staying still.
 */
@Component({
  selector: 'app-watch-list',
  imports: [EpisodeCard, EpisodesTabs, EmptyState, Skeleton, MatIcon, PullToLoad, LoadError],
  templateUrl: './watch-list.html',
  styles: `
    /* A section's title as a full-width button folding it: the title, its count, then a chevron. */
    .section-toggle {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      min-height: 48px;
      margin-top: 16px;
      padding: 0 16px;
      border: 0;
      background: none;
      color: var(--mat-sys-on-surface-variant);
      font: var(--mat-sys-title-small);
      letter-spacing: 0.06em;
      text-align: start;
      text-transform: uppercase;
      cursor: pointer;
    }
    .section-toggle:focus-visible {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -4px;
    }
    .count {
      font-variant-numeric: tabular-nums;
      letter-spacing: normal;
    }
    .chevron {
      margin-inline-start: auto;
      transform: rotate(-90deg);
      transition: transform var(--duration-medium) var(--ease-emph-decel);
    }
    .chevron.open {
      transform: none;
    }
    .history-toggle {
      align-self: flex-end;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class WatchList {
  protected readonly translate = injectTranslator('app');
  protected readonly routes = appRoutes;
  protected readonly store = inject(WatchListStore);
  private readonly timeZone = inject(AuthStore).$timeZone;
  protected readonly $mode = inject(ViewModes).mode('watchList');
  protected readonly $failed = signal(false);
  private readonly collapsedSections = inject(CollapsedSections);

  private readonly historyBlock = viewChild.required<ElementRef<HTMLElement>>('history');

  protected readonly actions: CardAction<SetAside>[] = [
    { id: 'watch_later', label: this.translate('app.status.watch_later'), icon: 'schedule' },
    { id: 'stopped', label: this.translate('app.common.stopWatching'), icon: 'block' },
  ];

  /** Watch next, Haven't watched for a while, Haven't started: each with its cards, folded or not; empty ones hidden. */
  protected readonly $sections = computed(() => {
    const episodes = this.store.episodes() ?? [];
    const collapsed = this.collapsedSections.collapsed();
    return Object.entries(SECTIONS)
      .map(([id, label]) => ({
        id,
        label: this.translate(label),
        episodes: episodes.filter((episode) => episode.section === id),
        open: !collapsed.has(`watchList:${id}`),
      }))
      .filter((section) => section.episodes.length > 0);
  });

  protected toggleSection(id: string): void {
    this.collapsedSections.toggle('watchList', id);
  }

  /** Oldest at the top, the newest right above the watch list. */
  protected readonly $history = computed(() =>
    this.store
      .history()
      .map((entry) => ({ entry, card: historyCard(entry), detail: formatDate(entry.watched_at, this.timeZone()) }))
      .reverse(),
  );

  constructor() {
    // Back and forward come back to the history as it was; any other visit opens on the watch list.
    if (inject(Router).currentNavigation()?.trigger !== 'popstate') this.store.resetHistory();
    this.load();

    const scroller = inject(CdkScrollable, { optional: true })?.getElementRef().nativeElement;
    let height: number | null = null;
    afterRenderEffect({
      earlyRead: () => {
        this.store.history();
        return this.historyBlock().nativeElement.offsetHeight;
      },
      write: (current) => {
        // What grew above the screen pushes the content down by as much: scroll by as much to keep it still.
        if (scroller && height !== null && current() > height) scroller.scrollTop += current() - height;
        height = current();
      },
    });
  }

  protected load(): void {
    this.$failed.set(false);
    this.store.load().subscribe({ error: () => this.$failed.set(true) });
  }

  /** Scrolling or pulling up from the top loads an older page of history, one at a time. */
  protected pulled(): void {
    if (this.store.historyState() === 'idle') this.store.loadOlderHistory();
  }
}
