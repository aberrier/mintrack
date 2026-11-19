import { Injectable, signal } from '@angular/core';
import { readStoredSet, writeStoredSet } from '../core/stored';

const STORAGE_KEY = 'mintrack.collapsed';

/** Sections the user folded, by screen, remembered on this device; every section starts open. */
@Injectable({ providedIn: 'root' })
export class CollapsedSections {
  private readonly $collapsed = signal(readStoredSet(STORAGE_KEY));

  /** Folded sections, as `screen:section`. */
  readonly collapsed = this.$collapsed.asReadonly();

  toggle(screen: string, section: string): void {
    const key = `${screen}:${section}`;
    const next = new Set(this.$collapsed());
    if (!next.delete(key)) next.add(key);
    this.$collapsed.set(next);
    writeStoredSet(STORAGE_KEY, next);
  }
}
