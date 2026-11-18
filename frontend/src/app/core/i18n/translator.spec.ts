import { injectTranslator } from '.';

describe('injectTranslator', () => {
  it('returns the English text of a path, available from the first render', () => {
    const translate = injectTranslator('app');

    expect(translate('app.upcoming.today')).toBe('Today');
  });

  it('fills the named placeholders', () => {
    const translate = injectTranslator('app');

    expect(translate('app.admin.link.intro', { username: 'alice' })).toBe(
      'Send this link to alice. It is shown only once.',
    );
  });
});
