import { TestBed } from '@angular/core/testing';
import { CollapsedSections } from './collapsed-sections';

describe('CollapsedSections', () => {
  beforeEach(() => localStorage.clear());

  it('starts with every section open, and remembers a folded one on the device', () => {
    const sections = TestBed.inject(CollapsedSections);
    expect(sections.collapsed().size).toBe(0);

    sections.toggle('watchList', 'dormant');

    expect(sections.collapsed().has('watchList:dormant')).toBe(true);
    TestBed.resetTestingModule();
    expect(TestBed.inject(CollapsedSections).collapsed().has('watchList:dormant')).toBe(true);
  });

  it('opens a folded section again', () => {
    const sections = TestBed.inject(CollapsedSections);

    sections.toggle('watchList', 'next');
    sections.toggle('watchList', 'next');

    expect(sections.collapsed().size).toBe(0);
  });
});
