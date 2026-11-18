import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { appRoutes } from '../../app.paths';
import { Poster } from '../../shared/poster';

/** One episode in a list, linking to its show: the poster and title, the episode code and title, and a detail. */
@Component({
  selector: 'app-episode-card',
  imports: [RouterLink, Poster],
  templateUrl: './episode-card.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EpisodeCard {
  readonly episode = input.required<Model.Http.UpcomingEpisode>();
  /** Shown on the right, such as the air time. */
  readonly detail = input<string | null>(null);

  protected readonly link = computed(() => appRoutes.show(this.episode().tmdb_id));

  protected readonly code = computed(() => {
    const { season_number, episode_number } = this.episode();
    return `S${pad(season_number)}E${pad(episode_number)}`;
  });
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}
