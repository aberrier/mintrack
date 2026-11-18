import { inject } from '@angular/core';
import { MatIconRegistry } from '@angular/material/icon';
import { DomSanitizer } from '@angular/platform-browser';
import check_circle from '@material-symbols/svg-400/outlined/check_circle-fill.svg';
import contentCopy from '@material-symbols/svg-400/outlined/content_copy.svg';
import home from '@material-symbols/svg-400/outlined/home.svg';
import more_vert from '@material-symbols/svg-400/outlined/more_vert.svg';
import person from '@material-symbols/svg-400/outlined/person.svg';
import radio_button_unchecked from '@material-symbols/svg-400/outlined/radio_button_unchecked.svg';
import search from '@material-symbols/svg-400/outlined/search.svg';
import video_library from '@material-symbols/svg-400/outlined/video_library.svg';

/** Icons are bundled SVGs registered by name: no icon font to download, only what is used ships. */
const icons = {
  check_circle,
  content_copy: contentCopy,
  home,
  more_vert,
  person,
  radio_button_unchecked,
  search,
  video_library,
} as const;

export type IconName = keyof typeof icons;

export function registerIcons(): void {
  const registry = inject(MatIconRegistry);
  const sanitizer = inject(DomSanitizer);
  for (const [name, svg] of Object.entries(icons)) {
    // Trusted: the files come from the @material-symbols package at build time, never from users.
    registry.addSvgIconLiteral(name, sanitizer.bypassSecurityTrustHtml(svg));
  }
}
