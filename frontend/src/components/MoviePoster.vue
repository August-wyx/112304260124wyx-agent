<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  path?: string | null
  title: string
  movieId?: string | number | null
  year?: number | string | null
  genres?: string[] | null
}>(), { path: null, movieId: null, year: null, genres: () => [] })

const stage = ref(0)
watch(() => [props.path, props.movieId], () => { stage.value = 0 })

const remoteSrc = computed(() => props.path && /^\/[a-zA-Z0-9._-]+\.(jpg|png|webp)$/.test(props.path)
  ? `https://image.tmdb.org/t/p/w342${props.path}` : null)
// Real posters fetched for the popular catalogue prefix live in frontend/public.
const localSrc = computed(() => props.movieId ? `/posters/${props.movieId}.jpg` : null)
const src = computed(() => {
  if (stage.value === 0 && localSrc.value) return localSrc.value
  if (stage.value <= 1 && remoteSrc.value) return remoteSrc.value
  return null
})
function onError() {
  stage.value = stage.value === 0 && remoteSrc.value ? 1 : 2
}

const cleanTitle = computed(() => props.title.replace(/\s*\(\d{4}\)\s*$/, ''))
const hash = computed(() => {
  const source = String(props.movieId ?? props.title)
  let value = 0
  for (const char of source) value = (value * 31 + char.charCodeAt(0)) % 100000
  return value
})

// Deterministic muted palette per film so every card has a distinct cover.
const palette = computed(() => {
  const palettes = [
    { a: '#0f1f1c', b: '#1d3a32', glow: '#3f6b56' },
    { a: '#131e26', b: '#22333f', glow: '#45657a' },
    { a: '#211a14', b: '#3a2c1e', glow: '#8a6a3c' },
    { a: '#1a1a20', b: '#2c2b36', glow: '#5b5570' },
  ]
  const tone = palettes[hash.value % palettes.length]
  return { '--poster-a': tone.a, '--poster-b': tone.b, '--poster-glow': tone.glow }
})
</script>
<template>
  <div class="movie-poster" :style="palette">
    <img v-if="src" :src="src" :alt="title + '海报'" loading="lazy" @error="onError" />
    <div v-else class="poster-placeholder" role="img" :aria-label="title + '：本地档案封面'">
      <span class="poster-grain" aria-hidden="true" />
      <span class="poster-eyebrow">CINELAB ARCHIVE</span>
      <span class="poster-year">{{ year || '—' }}</span>
      <span class="poster-title-block">
        <i class="poster-rule" aria-hidden="true" />
        <strong class="poster-title">{{ cleanTitle }}</strong>
        <span class="poster-genres">{{ (genres || []).slice(0, 2).join(' · ') || 'FILM' }}</span>
      </span>
      <span class="poster-id">#{{ movieId ?? '—' }}</span>
    </div>
  </div>
</template>
<style scoped>
.movie-poster{position:relative;container-type:inline-size;aspect-ratio:2/3;background:var(--poster-a);border:1px solid #31413e;border-radius:6px;overflow:hidden}
.movie-poster img{width:100%;height:100%;object-fit:cover;display:block}
.poster-placeholder{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:space-between;padding:7cqw 7cqw 6cqw;background:radial-gradient(130% 90% at 18% 0%,color-mix(in srgb,var(--poster-glow) 55%,transparent),transparent 62%),linear-gradient(158deg,var(--poster-a),var(--poster-b));color:#efe6d4}
.poster-grain{position:absolute;inset:0;opacity:.16;background:repeating-linear-gradient(115deg,#fff0 0 3px,#ffffff0d 3px 4px),repeating-linear-gradient(25deg,#0000 0 6px,#0000001a 6px 7px);pointer-events:none}
.poster-eyebrow{position:relative;font-size:3.4cqw;letter-spacing:.18em;color:#d9c7a2;opacity:.72;white-space:nowrap}
.poster-year{position:absolute;top:7cqw;right:7cqw;font-family:Georgia,serif;font-size:4.6cqw;color:#dfb76c;opacity:.9}
.poster-title-block{position:relative;display:flex;flex-direction:column;gap:3.4cqw;padding-bottom:1cqw}
.poster-rule{display:block;width:26%;height:1px;background:#dfb76c}
.poster-title{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;font-family:Georgia,serif;font-size:9.6cqw;line-height:1.18;letter-spacing:.01em;text-shadow:0 1px 12px #00000066}
.poster-genres{font-size:3.2cqw;letter-spacing:.12em;color:#c9b894;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.poster-id{position:relative;align-self:flex-end;font-family:monospace;font-size:3.2cqw;color:#c9b894;opacity:.6}
</style>
