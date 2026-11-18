import { Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'mintrack.collapsed';

/**
 * Sections the user folded, by screen, remembered on this device; every section starts open. Storage may be
 * unavailable (private browsing, blocked site data): the choice then lasts until the app reloads.
 */
@Injectable({ providedIn: 'root' })
export class CollapsedSections {
  private readonly $collapsed = signal<ReadonlySet<string>>(read());

  /** Folded sections, as `screen:section`. */
  readonly collapsed = this.$collapsed.asReadonly();

  toggle(screen: string, section: string): void {
    const key = `${screen}:${section}`;
    const next = new Set(this.$collapsed());
    if (!next.delete(key)) next.add(key);
    this.$collapsed.set(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
    } catch {
      // Kept in memory only.
    }
  }
}

function read(): ReadonlySet<string> {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    return new Set(Array.isArray(saved) ? saved.filter((key) => typeof key === 'string') : []);
  } catch {
    return new Set();
  }
}
