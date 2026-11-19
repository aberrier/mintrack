import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  input,
  output,
  viewChild,
} from '@angular/core';
import { MatIconButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { MatMenu, MatMenuItem, MatMenuTrigger } from '@angular/material/menu';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../app.paths';
import { injectTranslator } from '../../core/i18n';
import { IconName } from '../../core/icons/icons';
import { episodeCode } from '../../core/tracking/episodes';
import { CheckButton } from '../check-button';
import { injectEpisodeSheet } from '../episode-sheet';
import { Poster } from '../poster';
import { SwipeActions } from '../swipe-actions';
import { ViewMode } from '../view-toggle';

const LONG_PRESS_MS = 500;
/** How far a finger may move before the press counts as a scroll. */
const SLOP_PX = 10;

/**
 * A finger held still on `element` for LONG_PRESS_MS runs `pressed`, while `enabled` says so; the browser's own menu
 * and the tap that ends the press are then cancelled. Must run in an injection context.
 */
function longPress(element: HTMLElement, enabled: () => boolean, pressed: () => void): void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let start: { x: number; y: number } | null = null;
  let fired = false;
  const cancel = () => {
    clearTimeout(timer);
    start = null;
  };
  const down = (event: PointerEvent) => {
    fired = false;
    if (event.pointerType !== 'touch' || !event.isPrimary || !enabled()) return;
    start = { x: event.clientX, y: event.clientY };
    timer = setTimeout(() => {
      start = null;
      fired = true;
      pressed();
    }, LONG_PRESS_MS);
  };
  const move = (event: PointerEvent) => {
    if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > SLOP_PX) cancel();
  };
  const click = (event: MouseEvent) => {
    if (!fired) return;
    fired = false;
    event.preventDefault();
    event.stopPropagation();
  };
  const contextMenu = (event: Event) => {
    if (start || fired) event.preventDefault();
  };
  const listeners: [string, EventListener, boolean][] = [
    ['pointerdown', down as EventListener, false],
    ['pointermove', move as EventListener, false],
    ['pointerup', cancel, false],
    ['pointercancel', cancel, false],
    ['click', click as EventListener, true],
    ['contextmenu', contextMenu, false],
  ];
  for (const [type, listener, capture] of listeners) element.addEventListener(type, listener, capture);
  inject(DestroyRef).onDestroy(() => {
    cancel();
    for (const [type, listener, capture] of listeners) element.removeEventListener(type, listener, capture);
  });
}

/** What a card shows: an episode of a show, or a movie when it has no season. */
export interface CardEpisode {
  tmdb_id: number;
  media_type?: Model.Http.MediaType;
  show_title: string;
  poster_path: string | null;
  season_number: number | null;
  episode_number: number | null;
  title: string | null;
  /** Aired and unwatched episodes after this one, shown as +N. */
  remaining?: number;
  /** The episode's id: tapping the episode opens its sheet. Absent for movies, which link to their page. */
  episode_id?: string;
  /** The user's stars, shown in a list. */
  stars?: number | null;
}

export interface CardAction<T extends string> {
  id: T;
  label: string;
  icon: IconName;
}

/** A watched episode or movie of the history, as a card. */
export function historyCard(entry: Model.Http.HistoryEntry): CardEpisode {
  return {
    tmdb_id: entry.tmdb_id,
    media_type: entry.media_type,
    show_title: entry.title,
    poster_path: entry.poster_path,
    season_number: entry.season_number,
    episode_number: entry.episode_number,
    title: entry.episode_title,
    episode_id: entry.media_type === 'tv' ? entry.id : undefined,
    stars: entry.stars,
  };
}

/** An episode of a show's page, as a card. */
export function showEpisodeCard(show: Model.Http.Show, episode: Model.Http.Episode, remaining: number): CardEpisode {
  return {
    tmdb_id: show.tmdb_id,
    show_title: show.title,
    poster_path: show.poster_path,
    season_number: episode.season_number,
    episode_number: episode.episode_number,
    title: episode.title,
    remaining,
    episode_id: episode.id,
  };
}

/**
 * One episode, linking to its show: in a list, the poster, show title, episode number and title; in a grid, the poster
 * with the episode number. Optionally a check that marks it in one tap, and actions offered by swiping the row left or
 * from its menu (the way in for keyboards, screen readers and mice).
 */
@Component({
  selector: 'app-episode-card',
  imports: [
    NgTemplateOutlet,
    RouterLink,
    Poster,
    CheckButton,
    SwipeActions,
    MatIconButton,
    MatIcon,
    MatMenu,
    MatMenuItem,
    MatMenuTrigger,
  ],
  templateUrl: './episode-card.html',
  styleUrl: './episode-card.css',
  host: { '[class.list]': "variant() === 'list'" },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EpisodeCard<T extends string = string> {
  protected readonly translate = injectTranslator('app');

  readonly episode = input.required<CardEpisode>();
  readonly variant = input<ViewMode>('list');
  /** Shown on the right in a list, such as the air time. */
  readonly detail = input<string | null>(null);
  /** Offer a check button that emits `check`. */
  readonly checkable = input(false);
  /** Show the episode as watched. */
  readonly watched = input(false);
  /** The show is finished: its poster carries the badge. */
  readonly finished = input(false);
  readonly actions = input<CardAction<T>[]>([]);
  /** Show the show's name above the episode in a list, unless the page is the show's. */
  readonly showTitle = input(true);

  readonly check = output<void>();
  readonly action = output<T>();

  private readonly menuTrigger = viewChild(MatMenuTrigger);

  protected readonly link = computed(() => {
    const { media_type = 'tv', tmdb_id } = this.episode();
    return appRoutes.media(media_type, tmdb_id);
  });

  protected readonly code = computed(() => {
    const { season_number, episode_number } = this.episode();
    return season_number === null || episode_number === null
      ? null
      : episodeCode(season_number, episode_number, this.variant() === 'grid');
  });

  /** The episode number as a screen reader says it: "season 1 episode 5". */
  private readonly spoken = computed(() => {
    const { season_number, episode_number } = this.episode();
    return season_number === null || episode_number === null
      ? null
      : this.translate('app.episodeCard.spoken', { season: String(season_number), episode: String(episode_number) });
  });

  /** The episode as a screen reader says it: "Show, season 1 episode 5, Title". */
  protected readonly name = computed(() =>
    [this.episode().show_title, this.spoken(), this.episode().title].filter(Boolean).join(', '),
  );

  protected readonly checkLabel = computed(() =>
    this.translate('app.episodeCard.check', { episode: this.spoken() ?? '', show: this.episode().show_title }),
  );

  constructor() {
    // On touch screens the grid shows only the check: a long press opens the actions.
    longPress(
      inject<ElementRef<HTMLElement>>(ElementRef).nativeElement,
      () => this.variant() === 'grid' && this.actions().length > 0,
      () => this.menuTrigger()?.openMenu(),
    );
  }

  protected readonly menuLabel = computed(() =>
    this.translate('app.episodeCard.actions', { show: this.episode().show_title }),
  );

  protected readonly openSheet = injectEpisodeSheet();

  protected readonly ratingLabel = computed(() =>
    this.translate('app.rating.yours', { count: String(this.episode().stars ?? 0) }),
  );
}
