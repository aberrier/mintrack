import { inject } from '@angular/core';
import { MatIconRegistry } from '@angular/material/icon';
import { DomSanitizer } from '@angular/platform-browser';
import add from '@material-symbols/svg-400/outlined/add.svg';
import admin_panel_settings_fill from '@material-symbols/svg-400/outlined/admin_panel_settings-fill.svg';
import admin_panel_settings from '@material-symbols/svg-400/outlined/admin_panel_settings.svg';
import arrow_back from '@material-symbols/svg-400/outlined/arrow_back.svg';
import block from '@material-symbols/svg-400/outlined/block.svg';
import calendar_month from '@material-symbols/svg-400/outlined/calendar_month.svg';
import check from '@material-symbols/svg-400/outlined/check.svg';
import check_circle_fill from '@material-symbols/svg-400/outlined/check_circle-fill.svg';
import check_circle from '@material-symbols/svg-400/outlined/check_circle.svg';
import close from '@material-symbols/svg-400/outlined/close.svg';
import cloud_off from '@material-symbols/svg-400/outlined/cloud_off.svg';
import contentCopy from '@material-symbols/svg-400/outlined/content_copy.svg';
import explore_fill from '@material-symbols/svg-400/outlined/explore-fill.svg';
import explore from '@material-symbols/svg-400/outlined/explore.svg';
import grid_view from '@material-symbols/svg-400/outlined/grid_view.svg';
import history from '@material-symbols/svg-400/outlined/history.svg';
import expand_more from '@material-symbols/svg-400/outlined/keyboard_arrow_down.svg';
import live_tv_fill from '@material-symbols/svg-400/outlined/live_tv-fill.svg';
import live_tv from '@material-symbols/svg-400/outlined/live_tv.svg';
import more_vert from '@material-symbols/svg-400/outlined/more_vert.svg';
import notifications from '@material-symbols/svg-400/outlined/notifications.svg';
import person_fill from '@material-symbols/svg-400/outlined/person-fill.svg';
import person from '@material-symbols/svg-400/outlined/person.svg';
import refresh from '@material-symbols/svg-400/outlined/refresh.svg';
import schedule from '@material-symbols/svg-400/outlined/schedule.svg';
import search from '@material-symbols/svg-400/outlined/search.svg';
import settings from '@material-symbols/svg-400/outlined/settings.svg';
import star_fill from '@material-symbols/svg-400/outlined/star-fill.svg';
import star from '@material-symbols/svg-400/outlined/star.svg';
import view_agenda from '@material-symbols/svg-400/outlined/view_agenda.svg';

/**
 * Icons are bundled SVGs registered by name: no icon font to download, only what is used ships. A `_fill` name is
 * the filled variant, shown for an active or done state.
 */
const icons = {
  add,
  admin_panel_settings,
  admin_panel_settings_fill,
  arrow_back,
  block,
  calendar_month,
  check,
  check_circle,
  check_circle_fill,
  close,
  cloud_off,
  content_copy: contentCopy,
  expand_more,
  explore,
  explore_fill,
  grid_view,
  history,
  live_tv,
  live_tv_fill,
  more_vert,
  notifications,
  person,
  person_fill,
  refresh,
  schedule,
  search,
  settings,
  star,
  star_fill,
  view_agenda,
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
