<script setup>
defineProps({
  name: { type: String, default: 'overview' },
  size: { type: [Number, String], default: 18 }
})
</script>

<template>
  <svg class="app-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <g stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <template v-if="name === 'overview'">
        <rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>
      </template>
      <template v-else-if="name === 'data' || name === 'sources'">
        <ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/>
      </template>
      <template v-else-if="name === 'jobs'">
        <path d="M9 4h6"/><path d="M9 2h6v4H9z"/><rect x="5" y="4" width="14" height="17" rx="2"/><path d="m8 12 2 2 5-5"/><path d="M8 17h8"/>
      </template>
      <template v-else-if="name === 'flow' || name === 'standard'">
        <circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6.5 7.5l4.2 8.6M17.5 7.5l-4.2 8.6"/>
      </template>
      <template v-else-if="name === 'types'">
        <path d="M4 5h16M4 12h10M4 19h16"/><circle cx="17" cy="12" r="3"/>
      </template>
      <template v-else-if="name === 'studio'">
        <path d="M8 4 3 9l5 5M16 4l5 5-5 5M14 2l-4 20"/>
      </template>
      <template v-else-if="name === 'resources'">
        <path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/><circle cx="12" cy="12" r="4"/>
      </template>
      <template v-else-if="name === 'knowledge'">
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z"/>
      </template>
      <template v-else-if="name === 'indexes' || name === 'index-profiles'">
        <circle cx="11" cy="11" r="7"/><path d="m20 20-4-4M8 8h6M8 11h6M8 14h3"/>
      </template>
      <template v-else-if="name === 'collections'">
        <rect x="3" y="5" width="14" height="14" rx="2"/><path d="M7 5V3h14v14h-4M7 9h6M7 13h6"/>
      </template>
      <template v-else-if="name === 'retrieval' || name === 'retrieval-profiles'">
        <circle cx="10" cy="10" r="6"/><path d="m14.5 14.5 5 5M7 10h6M10 7v6"/>
      </template>
      <template v-else-if="name === 'application' || name === 'application-access'">
        <path d="M8 7V4M16 7V4M6 7h12v5a6 6 0 0 1-12 0zM12 18v4"/><path d="M9 22h6"/>
      </template>
      <template v-else-if="name === 'ai-applications'">
        <rect x="4" y="6" width="16" height="13" rx="3"/><path d="M9 2h6M12 2v4M8 12h.01M16 12h.01M9 16h6"/>
      </template>
      <template v-else-if="name === 'search'">
        <circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>
      </template>
      <template v-else-if="name === 'plus'">
        <path d="M12 5v14M5 12h14"/>
      </template>
      <template v-else-if="name === 'menu'">
        <path d="M4 6h16M4 12h16M4 18h16"/>
      </template>
      <template v-else-if="name === 'panel'">
        <rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M14 9l-3 3 3 3"/>
      </template>
      <template v-else>
        <circle cx="12" cy="12" r="8"/><path d="M9 12h6"/>
      </template>
    </g>
  </svg>
</template>
