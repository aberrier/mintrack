import { injectTranslator } from '.';

describe('injectTranslator', () => {
  it('returns the English text of a path, available from the first render', () => {
    const translate = injectTranslator('app');

    expect(translate('app.home.status.online')).toBe('Online');
  });
});
