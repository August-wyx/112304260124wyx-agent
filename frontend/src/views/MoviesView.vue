<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import http from '../api'
import { useRemote } from '../composables/useRemote'
import { genreLabel } from '../genres'
import type { Movie, Page } from '../types'
import MovieCard from '../components/MovieCard.vue'
import StatePanel from '../components/StatePanel.vue'
import PageNav from '../components/PageNav.vue'
const route = useRoute(), router = useRouter()
const q = ref(''), selectedGenres = ref<string[]>([]), genres = ref<string[]>([])
const genreError = ref<unknown>(null)
const { data, error, loading, load } = useRemote<Page<Movie>>()
const page = computed(() => Math.max(1, Math.min(100000, Number(route.query.page) || 1)))
const quickGenres = computed(() => genres.value.slice(0, 10))
const genresParam = computed(() => selectedGenres.value.join(','))
async function fetchGenres() { try { genres.value = (await http.get<{items:string[]}>('/genres')).data.items; genreError.value = null } catch (e) { genreError.value = e } }
function fetchMovies() { return load(async () => (await http.get<Page<Movie>>('/movies', { params: { page: page.value, per_page: 12, ...(q.value ? { q: q.value } : {}), ...(genresParam.value ? { genres: genresParam.value } : {}) } })).data) }
function search(nextPage = 1) {
  void router.push({ path: '/movies', query: { ...(q.value ? { q: q.value } : {}), ...(genresParam.value ? { genres: genresParam.value } : {}), ...(nextPage > 1 ? { page: nextPage } : {}) } })
  if (nextPage === page.value && q.value === (route.query.q || '') && genresParam.value === (route.query.genres || '')) void fetchMovies()
}
function toggleGenre(value: string) {
  const i = selectedGenres.value.indexOf(value)
  if (i >= 0) selectedGenres.value.splice(i, 1); else selectedGenres.value.push(value)
  search()
}
function clearGenres() { if (selectedGenres.value.length) { selectedGenres.value = []; search() } }
watch(() => route.fullPath, () => {
  q.value = typeof route.query.q === 'string' ? route.query.q : ''
  const g = route.query.genres
  selectedGenres.value = typeof g === 'string' && g ? g.split(',').filter(Boolean) : []
  void fetchMovies()
}, { immediate: true })
void fetchGenres()
</script>
<template>
  <div class="page movies-page">
    <section class="library-head">
      <div><p class="eyebrow">HUWEN LIBRARY</p><h1>电影库<span class="heading-dot">.</span></h1><p>片名、年代、类型，总有一种方式让你遇见好电影。</p></div>
      <div class="library-stat"><strong>{{ data ? data.total.toLocaleString() : '—' }}</strong><span>部真实电影</span><small>MOVIELENS ARCHIVE</small></div>
    </section>

    <form class="filter-bar library-filter" @submit.prevent="search()">
      <div class="search-field"><label for="movie-search">搜索片名</label><el-input id="movie-search" v-model="q" :maxlength="100" placeholder="输入中文或原始片名" :prefix-icon="Search" clearable /></div>
      <div class="genre-field"><label for="genre-select">电影类型（可多选）</label><el-select id="genre-select" v-model="selectedGenres" placeholder="全部类型" multiple collapse-tags collapse-tags-tooltip clearable><el-option v-for="value in genres" :key="value" :label="genreLabel(value)" :value="value" /></el-select></div>
      <el-button type="primary" native-type="submit" :loading="loading">搜索电影</el-button>
    </form>

    <div v-if="quickGenres.length" class="quick-genres">
      <span class="quick-label">快速筛选</span>
      <button v-for="value in quickGenres" :key="value" type="button" :class="{ active: selectedGenres.includes(value) }" @click="toggleGenre(value)">{{ genreLabel(value) }}</button>
      <button v-if="selectedGenres.length" type="button" class="clear" @click="clearGenres">清除筛选（{{ selectedGenres.length }}）</button>
    </div>
    <StatePanel v-if="genreError" :error="genreError" @retry="fetchGenres" />
    <div class="result-caption"><span>{{ data ? `${data.total.toLocaleString()} 部电影` : '电影档案' }}</span><span>{{ selectedGenres.length ? `类型：${selectedGenres.map(genreLabel).join('、')}` : '原始编号升序' }} · 每页 12 部</span></div>
    <StatePanel :loading="loading" :error="error" :empty="!!data && !data.items.length" title="没有找到匹配的电影" description="尝试简短片名，或清除类型筛选。" @retry="fetchMovies"><div class="movie-grid"><MovieCard v-for="movie in data?.items" :key="movie.movie_id" :movie="movie" /></div></StatePanel>
    <PageNav :page="page" :total="data?.total || 0" @change="search" />
  </div>
</template>
<style scoped>
.movies-page{padding-top:32px}
.library-head{display:flex;justify-content:space-between;align-items:flex-end;gap:28px;margin-bottom:26px;flex-wrap:wrap}
.library-head h1{font-family:var(--font-display);font-size:clamp(34px,4vw,52px);margin-bottom:10px}
.library-head>div>p:last-child{color:var(--muted);font-size:14px}
.library-stat{display:flex;flex-direction:column;align-items:flex-end;gap:2px;border-left:1px solid var(--border);padding-left:24px}
.library-stat strong{font-family:Georgia,serif;font-size:38px;line-height:1;color:var(--accent)}
.library-stat span{font-size:11px;color:var(--muted)}
.library-stat small{font-size:9px;letter-spacing:.2em;color:#6f7b8b;margin-top:4px}
.library-filter{border-radius:14px;background:linear-gradient(120deg,#151b25,#121822);border-color:var(--border)}
.filter-bar{display:flex;align-items:flex-end;gap:16px;padding:20px 22px;flex-wrap:wrap}
.filter-bar label{display:block;font-size:11px;letter-spacing:.08em;color:var(--muted);margin-bottom:8px}
.search-field{flex:1;min-width:220px}
.genre-field{width:190px}
.quick-genres{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:16px}
.quick-label{font-size:10px;letter-spacing:.16em;color:var(--muted);margin-right:4px}
.quick-genres button{border:1px solid var(--border);background:#ffffff05;color:var(--muted);border-radius:999px;padding:5px 13px;font-size:12px;transition:border-color .18s,color .18s,background .18s}
.quick-genres button:hover{color:var(--text);border-color:#f06a5066}
.quick-genres button.active{color:var(--accent);border-color:var(--accent);background:var(--accent-tint)}
.quick-genres button.clear{color:var(--gold);border-style:dashed}
@media(max-width:780px){.library-stat{border-left:0;padding-left:0;align-items:flex-start}.library-stat strong{font-size:30px}.search-field{flex-basis:100%}.genre-field{flex:1;width:auto}.filter-bar .el-button{width:100%}}
@media(max-width:540px){.movies-page{padding-top:22px}.library-head{margin-bottom:20px}.quick-genres{gap:6px}.quick-genres button{padding:4px 10px;font-size:11px}}
</style>
