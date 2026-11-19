import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MATERIAL_ANIMATIONS } from '@angular/material/core';
import { provideRouter } from '@angular/router';
import { ApiTokens } from './api-tokens';

const token: Model.Http.ApiToken = {
  id: '6f1c',
  name: 'Claude',
  created_at: '2026-11-18T12:00:00Z',
  last_used_at: null,
};

describe('ApiTokens', () => {
  beforeEach(() =>
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: MATERIAL_ANIMATIONS, useValue: { animationsDisabled: true } },
      ],
    }),
  );

  async function render(tokens: Model.Http.ApiToken[]) {
    const fixture = TestBed.createComponent(ApiTokens);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('/api/api-tokens').flush(tokens);
    await fixture.whenStable();
    return { element: fixture.nativeElement as HTMLElement, http, fixture };
  }

  function button(root: ParentNode, label: string): HTMLButtonElement {
    return [...root.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)!;
  }

  it('lists the tokens without their value', async () => {
    const { element } = await render([token]);

    expect(element.querySelector('li')?.textContent).toContain('Claude');
    expect(element.querySelector('li')?.textContent).toContain('never used');
  });

  it('shows a created token once, then lists it', async () => {
    const { element, http, fixture } = await render([]);
    const input = element.querySelector('input')!;
    input.value = '  Claude  ';
    input.dispatchEvent(new Event('input'));
    element.querySelector('form')!.dispatchEvent(new Event('submit'));

    const create = http.expectOne({ method: 'POST', url: '/api/api-tokens' });
    expect(create.request.body).toEqual({ name: 'Claude' });
    create.flush({ ...token, token: 'mt_secret' });
    TestBed.tick();
    http.expectOne('/api/api-tokens').flush([token]);
    await fixture.whenStable();

    expect(element.querySelector('[data-testid="new-api-token"]')?.textContent).toBe('mt_secret');
    button(element, 'Done').click();
    await fixture.whenStable();
    expect(element.querySelector('[data-testid="new-api-token"]')).toBeNull();
    expect(element.querySelector('li')?.textContent).toContain('Claude');
  });

  it('revokes a token only after confirming', async () => {
    const { element, http, fixture } = await render([token]);

    button(element, 'Revoke').click();
    await fixture.whenStable();
    button(document, 'Cancel').click();
    await fixture.whenStable();
    http.expectNone({ method: 'DELETE' });

    button(element, 'Revoke').click();
    await fixture.whenStable();
    button(document.querySelector('mat-dialog-container')!, 'Revoke').click();
    await fixture.whenStable();
    http.expectOne({ method: 'DELETE', url: '/api/api-tokens/6f1c' }).flush(null);
    TestBed.tick();
    http.expectOne('/api/api-tokens').flush([]);
    await fixture.whenStable();

    expect(element.querySelector('li')?.textContent).toContain('No tokens yet.');
  });
});
