import { readStored, readStoredSet, writeStored, writeStoredSet } from './stored';

describe('stored choices', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('keeps a set of strings and ignores anything else saved under its key', () => {
    writeStoredSet('test.set', new Set(['a', 'b']));
    expect([...readStoredSet('test.set')]).toEqual(['a', 'b']);

    localStorage.setItem('test.set', '[1, "c", null]');
    expect([...readStoredSet('test.set')]).toEqual(['c']);

    localStorage.setItem('test.set', 'not json');
    expect(readStoredSet('test.set').size).toBe(0);
  });

  it('reads nothing and drops writes when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    expect(() => writeStored('test.value', 'on')).not.toThrow();
    expect(readStored('test.value')).toBeNull();
    expect(readStoredSet('test.set').size).toBe(0);
  });
});
