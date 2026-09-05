<template>
  <!-- Renders the approved photo frame. `src` comes from the listing_photo table
       (see the Census Data Source Specification for the storage contract); the
       placeholder is the approved empty state, not a dev stub. -->
  <img v-if="src" :src="src" :alt="placeholder" :style="imgStyle" />
  <div v-else :style="emptyStyle">
    <span style="font-family: var(--rf-display); font-size: 9px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: #339dde; padding: 0 8px; text-align: center;">
      {{ placeholder }}
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  id: { type: String, default: '' },
  src: { type: String, default: '' },
  placeholder: { type: String, default: 'Photo' },
  shape: { type: String, default: 'rect' }
});

const radius = computed(() => (props.shape === 'circle' ? '999px' : props.shape === 'rounded' ? '8px' : '0'));
const imgStyle = computed(() => 'display: block; width: 100%; height: 100%; object-fit: cover; border-radius: ' + radius.value + ';');
const emptyStyle = computed(() => 'width: 100%; height: 100%; display: grid; place-items: center; background: var(--rf-band); border-radius: ' + radius.value + ';');
</script>
