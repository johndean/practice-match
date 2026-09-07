import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import App from '../App.vue';

// Every route renders the single approved component; the URL is a mirror of
// state.screen (+ detailId / adminTab). See router/sync.ts.
export const routes: RouteRecordRaw[] = [
  { path: '/', component: App },
  { path: '/browse', component: App },
  { path: '/practices/:id', component: App },
  { path: '/requests', component: App },
  { path: '/seller', component: App },
  { path: '/admin', component: App },
  { path: '/:pathMatch(.*)*', redirect: '/' }
];

export const router = createRouter({ history: createWebHistory(), routes });
