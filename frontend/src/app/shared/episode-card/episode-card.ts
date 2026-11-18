import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIconButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { MatMenu, MatMenuItem, MatMenuTrigger } from '@angular/material/menu';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../app.paths';
import { injectTranslator } from '../../core/i18n';
import { IconName } from '../../core/icons/icons';
import { episodeCode } from '../../core/tracking/episodes';
import { CheckMark } from '../check-mark';
import { Poster } from '../poster';
import { SwipeActions } from '../swipe-actions';
import { ViewMode } from '../view-toggle';

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
}

export interface CardAction {
  id: string;
  label: string;
  icon: IconName;
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
    CheckMark,
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
export class EpisodeCard {
  protected readonly translate = injectTranslator('app');

  readonly episode = input.required<CardEpisode>();
  readonly variant = input<ViewMode>('list');
  /** Shown on the right in a list, such as the air time. */
  readonly detail = input<string | null>(null);
  /** Offer a check button that emits `check`. */
  readonly checkable = input(false);
  /** Show the episode as watched. */
  readonly watched = input(false);
  readonly actions = input<CardAction[]>([]);

  readonly check = output<void>();
  readonly action = output<string>();

  protected readonly link = computed(() => {
    const { media_type, tmdb_id } = this.episode();
    return media_type === 'movie' ? appRoutes.movie(tmdb_id) : appRoutes.show(tmdb_id);
  });

  protected readonly code = computed(() => {
    const { season_number, episode_number } = this.episode();
    return season_number === null || episode_number === null ? null : episodeCode(season_number, episode_number);
  });

  /** The episode as a screen reader says it: "Show, S01 | E05, Title". */
  protected readonly name = computed(() =>
    [this.episode().show_title, this.code(), this.episode().title].filter(Boolean).join(', '),
  );

  protected readonly checkLabel = computed(() =>
    this.translate('app.episodeCard.check', { episode: this.code() ?? '', show: this.episode().show_title }),
  );

  protected readonly menuLabel = computed(() =>
    this.translate('app.episodeCard.actions', { show: this.episode().show_title }),
  );
}
