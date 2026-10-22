<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { genreLabels } from '../genres'

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

// Deterministic ink-and-vermilion covers so every card has a distinct fallback.
const palette = computed(() => {
  const palettes = [
    { a: '#101722', b: '#1d2a3a', glow: '#f06a50' },
    { a: '#141827', b: '#26304a', glow: '#8b8fd8' },
    { a: '#1d1710', b: '#3a2b1c', glow: '#e6c07c' },
    { a: '#121a1a', b: '#223634', glow: '#63a89a' },
  ]
  const tone = palettes[hash.value % palettes.length]
  return { '--poster-a': tone.a, '--poster-b': tone.b, '--poster-glow': tone.glow }
})
const genreText = computed(() => genreLabels(props.genres, 2).join(' · ') || '华文影像')
</script>
<template>
  <div class="movie-poster" :style="palette">
    <img v-if="src" :src="src" :alt="title + '海报'" loading="lazy" @error="onError" />
    <div v-else class="poster-placeholder" role="img" :aria-label="title + '：华文影视资料封面'">
      <span class="poster-grain" aria-hidden="true" />
      <span class="poster-eyebrow">华文影视 · 资料馆</span>
      <span class="poster-year">{{ year || '—' }}</span>
      <span class="poster-title-block">
        <i class="poster-rule" aria-hidden="true" />
        <strong class="poster-title">{{ cleanTitle }}</strong>
        <span class="poster-genres">{{ genreText }}</span>
      </span>
      <span class="poster-id">NO. {{ movieId ?? '—' }}</span>
    </div>
  </div>
</template>
<style scoped>
.movie-poster{position:relative;container-type:inline-size;aspect-ratio:2/3;background:var(--poster-a);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.movie-poster img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s cubic-bezier(.2,.7,.3,1)}
.poster-placeholder{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:space-between;padding:7cqw 7cqw 6cqw;background:radial-gradient(130% 90% at 18% 0%,color-mix(in srgb,var(--poster-glow) 48%,transparent),transparent 62%),linear-gradient(158deg,var(--poster-a),var(--poster-b));color:#f0e8da}
.poster-grain{position:absolute;inset:0;opacity:.14;background:repeating-linear-gradient(115deg,#fff0 0 3px,#ffffff0d 3px 4px),repeating-linear-gradient(25deg,#0000 0 6px,#0000001a 6px 7px);pointer-events:none}
.poster-eyebrow{position:relative;font-size:3.2cqw;letter-spacing:.16em;color:#d9cdb9;opacity:.75;white-space:nowrap}
.poster-year{position:absolute;top:7cqw;right:7cqw;font-family:Georgia,serif;font-size:4.6cqw;color:var(--gold);opacity:.92}
.poster-title-block{position:relative;display:flex;flex-direction:column;gap:3.2cqw;padding-bottom:1cqw}
.poster-rule{display:block;width:24%;height:1px;background:var(--accent)}
.poster-title{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;font-family:var(--font-display);font-size:9.2cqw;line-height:1.24;letter-spacing:.02em;text-shadow:0 1px 12px #00000066}
.poster-genres{font-size:3.2cqw;letter-spacing:.08em;color:#c8bda9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.poster-id{position:relative;align-self:flex-end;font-family:monospace;font-size:3cqw;color:#c8bda9;opacity:.6}
</style>
