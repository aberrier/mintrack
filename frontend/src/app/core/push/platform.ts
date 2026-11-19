/** The phone systems the notifications guide covers. */
export type PhonePlatform = 'android' | 'ios';

/**
 * The guide's sections, the visitor's system first. iPadOS reports a Mac user agent, told apart by its touch screen;
 * Safari on iOS also defines `navigator.standalone`. Other systems get Android first.
 */
export function platformsFor(nav: Pick<Navigator, 'userAgent' | 'maxTouchPoints'>): PhonePlatform[] {
  const ios =
    /iPhone|iPad|iPod/.test(nav.userAgent) ||
    (/Macintosh/.test(nav.userAgent) && nav.maxTouchPoints > 1) ||
    'standalone' in nav;
  return ios ? ['ios', 'android'] : ['android', 'ios'];
}
