import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  input,
  linkedSignal,
  output,
  signal,
} from '@angular/core';
import { MatButton } from '@angular/material/button';
import { MatFormField, MatHint, MatLabel } from '@angular/material/form-field';
import { MatIcon } from '@angular/material/icon';
import { MatInput } from '@angular/material/input';
import { MatSnackBarRef, TextOnlySnackBar } from '@angular/material/snack-bar';
import { Observable } from 'rxjs';
import { ApiService, RatingTarget } from '../core/api/api.service';
import { LOCALE } from '../core/dates';
import { AppTranslate, injectTranslator } from '../core/i18n';
import { injectNotify, injectNotifyUndo } from '../core/notify';

/** TMDB's score of a show, a movie or an episode in words, or null when nobody voted. */
export function tmdbScore(
  translate: AppTranslate,
  media: Pick<Model.Http.Media, 'vote_average' | 'vote_count'> | undefined,
): string | null {
  if (!media?.vote_count || media.vote_average === null) return null;
  return translate('app.rating.tmdbScore', {
    score: media.vote_average.toFixed(1),
    votes: media.vote_count.toLocaleString(LOCALE),
  });
}

/** The API's limit of a review's length. */
const MAX_REVIEW_LENGTH = 500;
const STARS = [1, 2, 3, 4, 5] as const;

/**
 * The user's own rating of a show, a movie or an episode: one row of five stars, an optional review and Save, with
 * Remove once rated. It saves on Save only, and says when the server took it or could not.
 */
@Component({
  selector: 'app-rating-form',
  imports: [MatButton, MatFormField, MatHint, MatIcon, MatInput, MatLabel],
  template: `
    <h3 class="[font:var(--mat-sys-title-medium)]">{{ translate('app.rating.title') }}</h3>
    <div class="stars" role="group" [attr.aria-label]="translate('app.rating.stars')">
      @for (value of stars; track value) {
        <button
          type="button"
          class="star"
          [class.on]="value <= $stars()"
          [attr.aria-pressed]="value === $stars()"
          [attr.aria-label]="translate('app.rating.star', { count: '' + value })"
          (click)="$stars.set(value)">
          <mat-icon [svgIcon]="value <= $stars() ? 'star_fill' : 'star'" aria-hidden="true" />
        </button>
      }
    </div>
    <mat-form-field class="w-full" subscriptSizing="dynamic">
      <mat-label>{{ translate('app.rating.review') }}</mat-label>
      <textarea
        matInput
        rows="2"
        [maxLength]="maxLength"
        [value]="$review()"
        (input)="$review.set($any($event.target).value)"></textarea>
      <mat-hint>{{ translate('app.rating.reviewHint') }}</mat-hint>
      <mat-hint align="end" class="tabular-nums">{{ $review().length }}/{{ maxLength }}</mat-hint>
    </mat-form-field>
    <div class="flex justify-end gap-2">
      @if (rating()) {
        <button matButton type="button" class="min-h-12" [disabled]="$saving()" (click)="remove()">
          {{ translate('app.rating.remove') }}
        </button>
      }
      <button matButton="filled" type="button" class="min-h-12" [disabled]="!$changed() || $saving()" (click)="save()">
        {{ translate('app.rating.save') }}
      </button>
    </div>
  `,
  host: { class: 'flex flex-col gap-3' },
  styles: `
    .stars {
      display: flex;
      margin-inline-start: -8px;
    }
    .star {
      display: grid;
      place-items: center;
      width: 48px;
      height: 48px;
      padding: 0;
      border: 0;
      border-radius: var(--mat-sys-corner-full);
      background: none;
      color: var(--mat-sys-on-surface-variant);
      cursor: pointer;
    }
    .star.on {
      color: var(--mat-sys-primary);
    }
    .star mat-icon {
      transition: transform var(--duration-short) var(--ease-emph-decel);
    }
    .star.on mat-icon {
      transform: scale(1.1);
    }
    .star:active mat-icon {
      transform: scale(0.85);
    }
    .star:focus-visible {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -4px;
    }
    @media (prefers-reduced-motion: reduce) {
      .star mat-icon {
        transition: none;
        transform: none !important;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RatingForm {
  private readonly api = inject(ApiService);
  private readonly notify = injectNotify();
  private readonly notifyUndo = injectNotifyUndo();
  protected readonly translate = injectTranslator('app');
  protected readonly stars = STARS;
  protected readonly maxLength = MAX_REVIEW_LENGTH;
  /** The Undo of a removal, which goes with the form: once it is gone, nothing would show the rating put back. */
  private undoRemoval?: MatSnackBarRef<TextOnlySnackBar>;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.undoRemoval?.dismiss());
  }

  /** What is rated. */
  readonly target = input.required<RatingTarget>();
  /** The rating saved so far. */
  readonly rating = input.required<Model.Http.Rating | null>();
  /** The server saved a rating, or removed it (null). */
  readonly saved = output<Model.Http.Rating | null>();

  protected readonly $stars = linkedSignal(() => this.rating()?.stars ?? 0);
  protected readonly $review = linkedSignal(() => this.rating()?.review ?? '');
  protected readonly $saving = signal(false);
  protected readonly $changed = computed(() => {
    const rating = this.rating();
    return this.$stars() > 0 && (this.$stars() !== rating?.stars || this.$review().trim() !== rating?.review);
  });

  protected save(): void {
    this.send(this.api.ratings.save(this.target(), { stars: this.$stars(), review: this.$review().trim() }), () =>
      this.notify(this.translate('app.rating.saved')),
    );
  }

  /** Remove the rating, with an Undo that saves it again. */
  protected remove(): void {
    const removed = this.rating();
    if (!removed) return;
    this.send(this.api.ratings.remove(this.target()), () => {
      this.undoRemoval = this.notifyUndo(this.translate('app.rating.removed'), () =>
        this.send(this.api.ratings.save(this.target(), { stars: removed.stars, review: removed.review }), () =>
          this.notify(this.translate('app.rating.saved')),
        ),
      );
    });
  }

  private send(request: Observable<Model.Http.Rating | void>, done: () => void): void {
    this.$saving.set(true);
    request.subscribe({
      next: (rating) => {
        this.$saving.set(false);
        done();
        this.saved.emit(rating ?? null);
      },
      error: () => {
        this.$saving.set(false);
        this.notify(this.translate('app.rating.failed'));
      },
    });
  }
}
