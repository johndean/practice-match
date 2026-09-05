import { createApp } from 'vue';
import { router } from './router/routes';
import './styles/tokens.css';
import './styles/global.css';
import { h } from 'vue';
import { RouterView } from 'vue-router';

// `app.use(router)` is what triggers the router's own first navigation (it calls
// `push(routerHistory.location)` from inside `install()`), and that first navigation is
// what resolves `router.isReady()`. Awaiting `isReady()` *before* `use(router)` waits on a
// promise nothing has started yet — a deadlock that never mounts the app in a real browser.
const app = createApp({ render: () => h(RouterView) }).use(router);
router.isReady().then(() => app.mount('#app'));
