import AxeBuilder from '@axe-core/playwright';
import { Page } from '@playwright/test';

/** Measures of whatever screen is open: layout, tap targets, accessibility. */
export class ScreenDriver {
  constructor(private readonly page: Page) {}

  /** True when nothing overflows the viewport horizontally. */
  async fitsWidth(): Promise<boolean> {
    return this.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  }

  /**
   * The visible buttons and links whose tap target is under 48px either way, as "text (width×height)". A Material
   * button's target includes its invisible touch area.
   */
  async smallTargets(): Promise<string[]> {
    return this.page.evaluate(() => {
      const small: string[] = [];
      for (const element of document.querySelectorAll<HTMLElement>('a[href], button')) {
        if (element.closest('[inert], [aria-hidden="true"]')) continue;
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        const touch = (
          element.closest('.mat-mdc-slide-toggle')?.querySelector('.mat-mdc-slide-toggle-touch-target') ??
          element.querySelector('.mat-mdc-button-touch-target')
        )?.getBoundingClientRect();
        const width = Math.max(box.width, touch?.width ?? 0);
        const height = Math.max(box.height, touch?.height ?? 0);
        if (width < 47.5 || height < 47.5) {
          const name = element.getAttribute('aria-label') ?? element.textContent?.trim() ?? element.tagName;
          small.push(`${name} (${Math.round(width)}×${Math.round(height)})`);
        }
      }
      return small;
    });
  }

  /** The visible icons drawn off the centre of the button that holds only them by more than 1px, as "name (dx, dy)". */
  async offCentreIcons(): Promise<string[]> {
    return this.page.evaluate(() => {
      const off: string[] = [];
      const centre = (box: DOMRect) => ({ x: box.left + box.width / 2, y: box.top + box.height / 2 });
      for (const icon of document.querySelectorAll<HTMLElement>('mat-icon')) {
        if (icon.closest('[inert], [aria-hidden="true"]:not(mat-icon)')) continue;
        const button = icon.closest<HTMLElement>('button, a[href], [role="button"]');
        if (!button || button.textContent?.trim()) continue;
        const iconBox = icon.getBoundingClientRect();
        const buttonBox = button.getBoundingClientRect();
        if (!iconBox.width || !buttonBox.width || getComputedStyle(icon).opacity === '0') continue;
        const name = button.getAttribute('aria-label') ?? icon.getAttribute('svgicon') ?? button.tagName;
        const dx = centre(iconBox).x - centre(buttonBox).x;
        const dy = centre(iconBox).y - centre(buttonBox).y;
        if (Math.abs(dx) > 1 || Math.abs(dy) > 1) off.push(`${name} (${dx.toFixed(1)}, ${dy.toFixed(1)})`);
      }
      return off;
    });
  }

  /** WCAG 2.1 A and AA violations axe finds, as "rule: target". */
  async accessibilityViolations(): Promise<string[]> {
    // Colours are measured once the entering cards and pages have faded in; a loading pulse never ends.
    await this.page.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((animation) => animation.effect?.getTiming().iterations !== Infinity)
          .map((animation) => animation.finished.catch(() => undefined)),
      ),
    );
    const results = await new AxeBuilder({ page: this.page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    return results.violations.flatMap((violation) =>
      violation.nodes.map((node) => `${violation.id}: ${node.target.join(' ')}`),
    );
  }
}
