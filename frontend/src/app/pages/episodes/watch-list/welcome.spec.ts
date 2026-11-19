import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { AuthStore } from '../../../core/auth/auth.store';
import { WelcomeChoice } from './welcome';

describe('WelcomeChoice', () => {
  const user = signal<Model.Http.User | null>(null);

  beforeEach(() => {
    localStorage.clear();
    user.set({ id: 'first', username: 'first', is_admin: true, timezone: 'UTC' });
    TestBed.configureTestingModule({ providers: [{ provide: AuthStore, useValue: { $user: user } }] });
  });

  it('remembers on the device that a user hid the welcome, for that user only', () => {
    const choice = TestBed.inject(WelcomeChoice);
    expect(choice.$hidden()).toBe(false);

    choice.hide();

    expect(choice.$hidden()).toBe(true);
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [{ provide: AuthStore, useValue: { $user: user } }] });
    const reloaded = TestBed.inject(WelcomeChoice);
    expect(reloaded.$hidden()).toBe(true);
    user.set({ id: 'second', username: 'second', is_admin: false, timezone: 'UTC' });
    expect(reloaded.$hidden()).toBe(false);
  });
});
