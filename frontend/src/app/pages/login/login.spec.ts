import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MATERIAL_ANIMATIONS } from '@angular/material/core';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { AuthStore } from '../../core/auth/auth.store';
import Login from './login';

const ADMIN: Model.Http.User = { id: '1', username: 'owner', is_admin: true, timezone: 'Europe/Paris' };
const PASSWORD = 'a long enough passphrase';

describe('Login', () => {
  beforeEach(() =>
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap({ next: '/discover' }) } },
        },
        { provide: MATERIAL_ANIMATIONS, useValue: { animationsDisabled: true } },
      ],
    }),
  );

  function fill(root: HTMLElement, name: string, value: string): void {
    const input = root.querySelector<HTMLInputElement>(`input[formcontrolname="${name}"]`)!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
  }

  it('shows no form until the server says which one, then creates the admin and opens the page asked for', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Login);
    const http = TestBed.inject(HttpTestingController);
    const element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();

    expect(element.querySelector('form')).toBeNull();
    http.expectOne('/api/auth/setup').flush({ open: true });
    await fixture.whenStable();

    expect(element.querySelector('h1')?.textContent?.trim()).toBe('Create the admin account');
    fill(element, 'username', 'owner');
    fill(element, 'password', PASSWORD);
    fill(element, 'confirm', PASSWORD);
    element.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();
    const request = http.expectOne('/api/auth/setup');
    expect(request.request.body).toEqual({
      username: 'owner',
      password: PASSWORD,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
    request.flush(ADMIN);
    await fixture.whenStable();

    expect(TestBed.inject(AuthStore).$user()).toEqual(ADMIN);
    expect(navigate).toHaveBeenCalledWith('/discover');
  });

  it('offers the login form when the server cannot say whether setup is open', async () => {
    const fixture = TestBed.createComponent(Login);
    fixture.detectChanges();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/setup')
      .flush('down', { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelector('h1')?.textContent?.trim()).toBe('Log in');
  });
});
