import { Location } from '@angular/common';
import { provideLocationMocks } from '@angular/common/testing';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { NavigationEnd, provideRouter, Router, RouterOutlet } from '@angular/router';
import { filter, firstValueFrom } from 'rxjs';
import { ScrollRestoration } from './scroll-restoration';

@Component({ template: '<div style="height: 5000px"></div>' })
class Tall {}

@Component({ template: '<div style="height: 5000px"></div><h2 id="imports">Imports</h2>' })
class Sections {}

@Component({
  imports: [RouterOutlet, ScrollRestoration],
  template: '<main appScrollRestoration style="height: 100px; overflow-y: auto"><router-outlet /></main>',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class Host {}

describe('ScrollRestoration', () => {
  it('restores the scroll position of a page on back, and starts new pages at the top', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideLocationMocks(),
        provideRouter([
          { path: 'list', component: Tall },
          { path: 'item', component: Tall },
        ]),
      ],
    });
    const fixture = TestBed.createComponent(Host);
    const main = (fixture.nativeElement as HTMLElement).querySelector('main')!;
    const router = TestBed.inject(Router);
    // Subscribes the router to back and forward.
    router.initialNavigation();
    // jsdom has no layout: scrollTop keeps whatever is assigned.
    await router.navigateByUrl('/list');
    await fixture.whenStable();
    main.scrollTop = 1200;

    await router.navigateByUrl('/item');
    await fixture.whenStable();
    expect(main.scrollTop).toBe(0);

    const restored = firstValueFrom(router.events.pipe(filter((event) => event instanceof NavigationEnd)));
    TestBed.inject(Location).back();
    await restored;
    await fixture.whenStable();
    expect(main.scrollTop).toBe(1200);
  });

  it('opens a new page at the element its fragment names, and at the top when none has that id', async () => {
    TestBed.configureTestingModule({
      providers: [provideLocationMocks(), provideRouter([{ path: 'settings', component: Sections }])],
    });
    const fixture = TestBed.createComponent(Host);
    const main = (fixture.nativeElement as HTMLElement).querySelector('main')!;
    const router = TestBed.inject(Router);
    // jsdom has no layout, nor scrollIntoView.
    const scrolledTo: string[] = [];
    const scrollIntoView = Element.prototype.scrollIntoView;
    onTestFinished(() => void (Element.prototype.scrollIntoView = scrollIntoView));
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolledTo.push(this.id);
    };
    main.scrollTop = 300;

    await router.navigateByUrl('/settings#imports');
    await fixture.whenStable();
    expect(scrolledTo).toEqual(['imports']);

    await router.navigateByUrl('/settings#unknown');
    await fixture.whenStable();
    expect(scrolledTo).toEqual(['imports']);
    expect(main.scrollTop).toBe(0);
  });
});
