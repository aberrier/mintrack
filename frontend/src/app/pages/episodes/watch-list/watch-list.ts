import { CdkScrollable } from '@angular/cdk/scrolling';
import {
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { MatIcon } from '@angular/material/icon';
import { Router } from '@angular/router';
import { appRoutes } from '../../../app.paths';
import { injectTranslator } from '../../../core/i18n';
import { WatchListStore } from '../../../core/tracking/watch-list.store';
import { EmptyState } from '../../../shared/empty-state';
import { CardAction, CardEpisode, EpisodeCard } from '../../../shared/episode-card/episode-card';
import { Skeleton } from '../../../shared/skeleton';
import { ViewModes } from '../../../shared/view-toggle';
import { EpisodesTabs } from '../episodes-tabs';

/** How close to the top, in pixels, scrolling loads the next page of history. */
const HISTORY_THRESHOLD_PX = 300;
/** How far a finger pulls down at the top before the history loads. */
const PULL_PX = 40;

/**
 * The next episode of each show in progress, watched lately or not for a while, each checked in one tap. Above it,
 * the watch history loads page by page as the user scrolls up from the top, the content they look at staying still.
 */
@Component({
  selector: 'app-watch-list',
  imports: [EpisodeCard, EpisodesTabs, EmptyState, Skeleton, MatIcon],
  templateUrl: './watch-list.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export default class WatchList {
  protected readonly translate = injectTranslator('app');
  protected readonly routes = appRoutes;
  protected readonly store = inject(WatchListStore);
  protected readonly $mode = inject(ViewModes).mode('watchList');
  protected readonly $failed = signal(false);

  private readonly historyBlock = viewChild.required<ElementRef<HTMLElement>>('history');

  protected readonly actions: CardAction[] = [
    { id: 'watch_later', label: this.translate('app.watchList.watchLater'), icon: 'schedule' },
    { id: 'stopped', label: this.translate('app.watchList.stop'), icon: 'block' },
  ];

  protected readonly $sections = computed(() => {
    const episodes = this.store.episodes() ?? [];
    return [
      {
        id: 'next',
        label: this.translate('app.watchList.next'),
        episodes: episodes.filter((e) => e.section === 'next'),
      },
      {
        id: 'dormant',
        label: this.translate('app.watchList.dormant'),
        episodes: episodes.filter((e) => e.section === 'dormant'),
      },
    ].filter((section) => section.episodes.length > 0);
  });

  /** Oldest at the top, the newest right above the watch list. */
  protected readonly $history = computed(() =>
    this.store
      .history()
      .map((entry) => ({ entry, card: historyCard(entry), detail: formatWatched(entry.watched_at) }))
      .reverse(),
  );

  constructor() {
    // Back and forward come back to the history as it was; any other visit opens on the watch list.
    if (inject(Router).currentNavigation()?.trigger !== 'popstate') this.store.resetHistory();
    this.store.load().subscribe({ error: () => this.$failed.set(true) });

    const scroller = inject(CdkScrollable, { optional: true })?.getElementRef().nativeElement;
    if (scroller) this.loadHistoryOnScrollUp(scroller);

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

  protected loadHistory(): void {
    this.store.loadOlderHistory();
  }

  protected onAction(episode: Model.Http.WatchListEpisode, action: string): void {
    this.store.remove(episode, action === 'stopped' ? 'stopped' : 'watch_later');
  }

  /** Wheel or finger pulling down at the very top, or scrolling near the top once the history shows. */
  private loadHistoryOnScrollUp(scroller: HTMLElement): void {
    let pullFrom: number | null = null;
    const canLoad = () => this.store.historyState() === 'idle';
    const scroll = () => {
      if (canLoad() && this.store.history().length > 0 && scroller.scrollTop < HISTORY_THRESHOLD_PX) this.loadHistory();
    };
    const wheel = (event: WheelEvent) => {
      if (canLoad() && event.deltaY < 0 && scroller.scrollTop <= 0) this.loadHistory();
    };
    const touchStart = (event: TouchEvent) => {
      pullFrom = scroller.scrollTop <= 0 ? event.touches[0].clientY : null;
    };
    const touchMove = (event: TouchEvent) => {
      if (pullFrom === null || event.touches[0].clientY - pullFrom < PULL_PX) return;
      pullFrom = null;
      if (canLoad()) this.loadHistory();
    };
    const options = { passive: true };
    scroller.addEventListener('scroll', scroll, options);
    scroller.addEventListener('wheel', wheel, options);
    scroller.addEventListener('touchstart', touchStart, options);
    scroller.addEventListener('touchmove', touchMove, options);
    inject(DestroyRef).onDestroy(() => {
      scroller.removeEventListener('scroll', scroll);
      scroller.removeEventListener('wheel', wheel);
      scroller.removeEventListener('touchstart', touchStart);
      scroller.removeEventListener('touchmove', touchMove);
    });
  }
}

function historyCard(entry: Model.Http.HistoryEntry): CardEpisode {
  return {
    tmdb_id: entry.tmdb_id,
    media_type: entry.media_type,
    show_title: entry.title,
    poster_path: entry.poster_path,
    season_number: entry.season_number,
    episode_number: entry.episode_number,
    title: entry.episode_title,
  };
}

/** The day something was watched, with the year only when it is not this year. */
function formatWatched(watchedAt: string): string {
  const date = new Date(watchedAt);
  const thisYear = date.getFullYear() === new Date().getFullYear();
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: thisYear ? undefined : 'numeric',
  }).format(date);
}
