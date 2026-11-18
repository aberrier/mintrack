import { inject, Injectable } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';
import { injectTranslator, TranslationPath } from './i18n';

/**
 * The browser tab names the page: "Watch list · MinTrack". A route's title is a translation path; a route without one
 * (a show or a movie) names itself with `setPage` once its content is loaded.
 */
@Injectable({ providedIn: 'root' })
export class AppTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private readonly translate = injectTranslator('app');

  override updateTitle(snapshot: RouterStateSnapshot): void {
    const path = this.buildTitle(snapshot) as TranslationPath<'app'> | undefined;
    if (path) this.setPage(this.translate(path));
  }

  setPage(name: string): void {
    this.title.setTitle(`${name} · MinTrack`);
  }
}
