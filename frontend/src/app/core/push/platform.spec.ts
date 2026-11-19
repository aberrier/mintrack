import { platformsFor } from './platform';

const ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile';
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile';
const MAC = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15';

describe('platformsFor', () => {
  it('puts the iPhone and iPad steps first on iOS and iPadOS', () => {
    expect(platformsFor({ userAgent: IPHONE, maxTouchPoints: 5 })).toEqual(['ios', 'android']);
    expect(platformsFor({ userAgent: MAC, maxTouchPoints: 5 })).toEqual(['ios', 'android']);
  });

  it('puts the Android steps first on Android and other systems', () => {
    expect(platformsFor({ userAgent: ANDROID, maxTouchPoints: 5 })).toEqual(['android', 'ios']);
    expect(platformsFor({ userAgent: MAC, maxTouchPoints: 0 })).toEqual(['android', 'ios']);
  });
});
