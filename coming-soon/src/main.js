import { createApp } from 'vue';
import App from './App.vue';
import { vHover } from './directives/hover.js';
import './styles/tokens.css';
import './styles/global.css';

createApp(App).directive("hover", vHover).mount("#app");
