/**
 * Choices remembered on this device. Storage may be unavailable (private browsing, blocked site data): reads then find
 * nothing and writes are dropped, so a choice lasts until the app reloads.
 */
export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Kept in memory only.
  }
}

/** A set of strings stored as a JSON array; anything else reads as an empty set. */
export function readStoredSet(key: string): ReadonlySet<string> {
  try {
    const saved: unknown = JSON.parse(readStored(key) ?? '[]');
    return new Set(Array.isArray(saved) ? saved.filter((item) => typeof item === 'string') : []);
  } catch {
    return new Set();
  }
}

export function writeStoredSet(key: string, values: ReadonlySet<string>): void {
  writeStored(key, JSON.stringify([...values]));
}
