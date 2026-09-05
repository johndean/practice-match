<template>
<div style="min-height: 100vh; display: flex; flex-direction: column; background: var(--vf-white);">

  <header style="flex: none; padding: 30px 44px; animation: cs-rise 700ms var(--easing-out) both;">
    <img src="/assets/vin-foundation-logo.png" alt="VIN Foundation" style="display: block; height: 46px; width: auto;">
  </header>

  <main style="flex: 1; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr)); align-items: stretch; gap: 0;">

    <div style="display: flex; align-items: center; padding: 30px 44px 70px;">
      <div style="width: 100%; max-width: 620px;">

        <div style="display: inline-flex; align-items: center; gap: 9px; animation: cs-rise 700ms var(--easing-out) 120ms both;">
          <span style="width: 7px; height: 7px; border-radius: 999px; background: var(--vf-accent); animation: cs-pulse 3.2s ease-in-out infinite;"></span>
          <span style="font-size: 11.5px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--vf-accent);">In development</span>
        </div>

        <h1 style="margin: 20px 0 0; font-size: clamp(38px, 4.4vw, 60px); line-height: 1.16; letter-spacing: -.01em; animation: cs-rise 800ms var(--easing-out) 200ms both;">Something new is coming from the VIN Foundation.</h1>

        <div style="height: 3px; width: 96px; margin: 30px 0 0; background: var(--vf-accent); transform-origin: left; animation: cs-rule 900ms var(--easing-out) 700ms both;"></div>

        <p style="max-width: 50ch; margin: 28px 0 0; font-size: 18px; line-height: 1.7; color: var(--vf-text); animation: cs-rise 800ms var(--easing-out) 320ms both;">We're building it now, with the profession in mind. Leave your email and we'll write to you once — the day it opens.</p>

        <div style="display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin: 30px 0 0; animation: cs-rise 800ms var(--easing-out) 380ms both;">
          <span style="flex: none; font-size: 11.5px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--vf-navy);">It's for</span>
          <button @click="v.poke" aria-label="Redacted — details not yet announced" style="display: flex; align-items: center; gap: 7px; padding: 4px 0; background: none; border: 0; cursor: pointer;">
            <template v-for="(b, $index) in v.blocks" :key="$index">
              <span :style="b.style"></span>
            </template>
          </button>
        </div>
        <p style="margin: 12px 0 0; font-size: 14px; font-style: italic; color: #6b7480; animation: cs-rise 800ms var(--easing-out) 440ms both;">{{ v.tease }}</p>

        <div style="margin: 34px 0 0; max-width: 540px; animation: cs-rise 800ms var(--easing-out) 500ms both;">

          <template v-if="v.isForm">
            <div>
              <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <input :value="v.email" @change="v.setEmail" @keydown="v.onKey" type="email" autocomplete="email" placeholder="you@practice.com" aria-label="Email address" :style="v.inputStyle">
                <button @click="v.submit" style="flex: none; height: 54px; padding: 0 26px; font-size: 15px; font-weight: 500; letter-spacing: .03em; color: var(--vf-white); background: var(--vf-navy); border: 0; border-radius: 6px; cursor: pointer; transition: background 150ms var(--easing-out);" v-hover="'background: #002a52;'">Notify me</button>
              </div>
              <template v-if="v.hasError">
                <div style="display: flex; align-items: center; gap: 9px; margin-top: 12px; font-size: 14px; color: var(--color-red);">
                  <span style="width: 5px; height: 5px; border-radius: 999px; background: var(--color-red); flex: none;"></span>{{ v.errorText }}
                </div>
              </template>
              <p style="margin: 16px 0 0; font-size: 13.5px; line-height: 1.6; color: #6b7480;">One message, when it launches. Nothing else, and never shared.</p>
            </div>
          </template>

          <template v-if="v.isDone">
            <div style="padding: 26px 28px; background: var(--vf-accent-bg); border-radius: 8px; animation: cs-rise 500ms var(--easing-out) both;">
              <div style="font-size: 11.5px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--vf-accent);">You're on the list</div>
              <div style="font-family: var(--vf-display); font-weight: 700; margin-top: 10px; font-size: 22px; color: var(--vf-navy); word-break: break-word;">{{ v.email }}</div>
              <p style="margin: 12px 0 0; font-size: 15px; line-height: 1.7; color: var(--vf-text);">We'll write to you the day it opens. Nothing before then.</p>
              <button @click="v.reset" style="margin-top: 18px; font-size: 13.5px; font-weight: 500; letter-spacing: .03em; color: var(--vf-accent); background: none; border: 0; padding: 0; cursor: pointer;" v-hover="'color: var(--vf-navy); text-decoration: underline;'">Use a different address</button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <div style="position: relative; overflow: hidden; background: var(--vf-accent-bg); min-height: 340px;">
      <div style="position: absolute; left: 50%; top: 50%; width: 420px; height: 420px; margin: -210px 0 0 -210px;">
        <template v-for="(r, $index) in v.rings" :key="$index">
          <span :style="r.style"></span>
        </template>
        <span style="position: absolute; left: 50%; top: 50%; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 999px; background: var(--vf-navy);"></span>
      </div>
      <div style="position: absolute; left: 0; right: 0; bottom: 34px; text-align: center; font-size: 11.5px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; color: var(--vf-navy);">We're here to help</div>
    </div>
  </main>

  <footer style="flex: none; display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap; padding: 22px 44px; background: var(--vf-navy); color: var(--vf-white);">
    <span style="font-size: 13.5px;">© 2026 VIN Foundation &middot; A 501(c)(3) nonprofit organization</span>
    <a href="https://vinfoundation.org" style="font-size: 13.5px; color: var(--vf-white);">vinfoundation.org</a>
  </footer>
</div>
</template>

<script setup>
import { computed, reactive } from 'vue';
import { Component } from './logic.js';
import { vHover } from './directives/hover.js';

// The approved logic runs verbatim; making `state` reactive reproduces the original
// render pass exactly.
const c = new Component();
c.state = reactive(c.state);
const v = computed(() => c.renderVals());
</script>
