import { createApp, h, type App } from 'vue';
import { RouterView, type Router } from 'vue-router';

// `app.use(router)` is what triggers the router's own first navigation (it calls
// `push(routerHistory.location)` from inside `install()`), and that first navigation is
// what resolves `router.isReady()`. Awaiting `isReady()` *before* `use(router)` waits on a
// promise nothing has started yet — a deadlock that never mounts the app in a real browser.
export async function bootstrap(router: Router, root: string | Element): Promise<App> {
  const app = createApp({ render: () => h(RouterView) }).use(router);
  await router.isReady();
  app.mount(root);
  return app;
}
