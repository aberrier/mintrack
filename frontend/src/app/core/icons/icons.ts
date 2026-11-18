import { inject } from '@angular/core';
import { MatIconRegistry } from '@angular/material/icon';
import { DomSanitizer } from '@angular/platform-browser';
import contentCopy from '@material-symbols/svg-400/outlined/content_copy.svg';
import home from '@material-symbols/svg-400/outlined/home.svg';
import person from '@material-symbols/svg-400/outlined/person.svg';

/** Icons are bundled SVGs registered by name: no icon font to download, only what is used ships. */
const icons = { home, person, content_copy: contentCopy } as const;

export type IconName = keyof typeof icons;

export function registerIcons(): void {
  const registry = inject(MatIconRegistry);
  const sanitizer = inject(DomSanitizer);
  for (const [name, svg] of Object.entries(icons)) {
    // Trusted: the files come from the @material-symbols package at build time, never from users.
    registry.addSvgIconLiteral(name, sanitizer.bypassSecurityTrustHtml(svg));
  }
}
