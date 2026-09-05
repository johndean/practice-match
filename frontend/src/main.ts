import { createApp } from 'vue';
import { router } from './router/routes';
import './styles/tokens.css';
import './styles/global.css';
import { h } from 'vue';
import { RouterView } from 'vue-router';

router.isReady().then(() => {
  createApp({ render: () => h(RouterView) }).use(router).mount('#app');
});
