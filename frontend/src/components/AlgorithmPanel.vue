<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import MoviePoster from './MoviePoster.vue'
import type { AlgorithmResult, Movie } from '../types'

const props = withDefaults(defineProps<{
  endpoint: string | null
  label: string
  algorithm?: string
  subject?: string
  profileGenres?: string[]
  emptySubject?: string
}>(), { algorithm: '', subject: '', profileGenres: () => [], emptySubject: '登录后体验' })

const loading = ref(false), error = ref<unknown>(null), unavailable = ref(false)
const result = ref<AlgorithmResult | null>(null)
const movies = ref<Record<string, Movie>>({})
let run = 0
onScopeDispose(() => { run++ })

const algorithmNames: Record<string, string> = {
  content: '内容推荐', itemcf: '协同过滤', als: '矩阵分解', popular: '热门推荐', cold_start: '冷启动',
}
const algorithmLabel = computed(() => algorithmNames[props.algorithm] ? `${algorithmNames[props.algorithm]} · ${props.algorithm}` : props.algorithm)

const rows = computed(() => (result.value?.items || []).map(item => ({
  ...item,
  movie: movies.value[item.movie_id] || null,
  percent: scorePercent(item.score),
  matched: matchedGenres(movies.value[item.movie_id]?.genres || []),
})))
const generated = computed(() => result.value ? new Date(result.value.generated_at).toLocaleString('zh-CN', { hour12: false }) : '')

function scorePercent(score: number | null) {
  const items = result.value?.items || []
  const values = items.map(item => item.score).filter((value): value is number => value !== null)
  if (score === null || !values.length) return 0
  const max = Math.max(...values)
  return max > 0 ? Math.max(4, Math.round(score / max * 100)) : 0
}
function matchedGenres(genres: string[]) {
  const profile = new Set(props.profileGenres.map(genre => genre.toLowerCase()))
  return genres.filter(genre => profile.has(genre.toLowerCase()))
}

async function attachMovies(items: AlgorithmResult['items']) {
  const missing = items.map(item => item.movie_id).filter(id => !movies.value[id])
  if (!missing.length) return
  const settled = await Promise.allSettled(missing.map(id => http.get<Movie>(`/movies/${encodeURIComponent(id)}`)))
  const next = { ...movies.value }
  settled.forEach((entry, index) => { if (entry.status === 'fulfilled') next[missing[index]] = entry.value.data })
  movies.value = next
}

async function load() {
  const seq = ++run
  error.value = null; result.value = null; unavailable.value = false; loading.value = false
  if (!props.endpoint) return
  loading.value = true
  try {
    const response = await http.get<AlgorithmResult>(props.endpoint)
    if (seq !== run) return
    result.value = response.data
    await attachMovies(response.data.items)
  } catch (e) {
    if (seq !== run) return
    if (e instanceof ApiError && e.status === 501 && e.code === 'ALGORITHM_NOT_IMPLEMENTED') unavailable.value = true
    else error.value = e
  } finally { if (seq === run) loading.value = false }
}
watch(() => props.endpoint, load, { immediate: true })
</script>
<template>
  <section class="algorithm-panel" :aria-label="label">
    <div class="section-top">
      <h3>{{ label }}</h3>
      <span class="small-label">CONTENT-BASED ENGINE</span>
    </div>
    <StatePanel :loading="loading" :error="error" @retry="load">
      <div v-if="!endpoint || unavailable" class="algorithm-empty" role="status">
        <div class="algorithm-symbol"><el-icon aria-hidden="true"><Connection /></el-icon></div>
        <div>
          <span class="status-pill">{{ !endpoint ? emptySubject : '尚未实现' }}</span>
          <h3>{{ !endpoint ? '选择观众，开始探索' : '下一部好电影，等待算法发现' }}</h3>
          <p>{{ !endpoint ? '先选择历史用户或登录注册账号。推荐功能等待算法接入。' : '该算法尚未注册，当前没有模型版本或推荐结果。' }}</p>
        </div>
        <RouterLink v-if="!endpoint && emptySubject === '登录后体验'" class="text-link" to="/login">前往登录 →</RouterLink>
      </div>
      <div v-else-if="result" class="recommendation-results">
        <header class="result-head">
          <div>
            <span class="status-pill">{{ algorithmLabel }}</span>
            <h3>{{ subject || '当前观众' }} · Top {{ result.items.length }}</h3>
            <p v-if="!result.items.length">这位观众的历史不足以形成内容画像，本次没有推荐结果。</p>
            <p v-else>依据真实历史评分的类型偏好生成，已排除看过的电影。</p>
          </div>
          <dl class="result-meta">
            <div><dt>模型版本</dt><dd>{{ result.model_version }}</dd></div>
            <div><dt>运行模式</dt><dd>{{ result.runtime_mode }}</dd></div>
            <div><dt>生成时间</dt><dd>{{ generated }}</dd></div>
          </dl>
        </header>
        <ol v-if="result.items.length" class="rec-list">
          <li v-for="row in rows" :key="row.movie_id" class="rec-card">
            <span class="rec-rank">{{ String(row.rank).padStart(2, '0') }}</span>
            <RouterLink class="rec-poster" :to="`/movies/${row.movie_id}`" :aria-label="`查看 ${row.movie?.movielens_title || row.movie_id} 详情`">
              <MoviePoster :path="row.movie?.poster_path" :title="row.movie?.movielens_title || `电影 ${row.movie_id}`" />
            </RouterLink>
            <div class="rec-body">
              <div class="rec-title">
                <RouterLink :to="`/movies/${row.movie_id}`">
                  <h4>{{ row.movie?.title_zh || row.movie?.movielens_title || `电影 #${row.movie_id}` }}</h4>
                </RouterLink>
                <span class="rec-year">{{ row.movie?.release_year || '年份未收录' }}</span>
              </div>
              <div class="rec-genres">
                <span v-for="genre in row.movie?.genres || []" :key="genre" :class="{ match: profileGenres.includes(genre) }">{{ genre }}</span>
                <span v-if="!row.movie" class="muted">电影 #{{ row.movie_id }}</span>
              </div>
              <div class="score-row">
                <span>内容匹配度</span>
                <div class="score-track" role="img" :aria-label="`匹配度 ${row.percent}%`"><i :style="{ width: row.percent + '%' }" /></div>
                <strong>{{ row.score === null ? '—' : row.score.toFixed(3) }}</strong>
              </div>
              <p v-if="row.matched.length" class="rec-why">与观众偏好类型重合：{{ row.matched.join(' / ') }}</p>
            </div>
          </li>
        </ol>
      </div>
    </StatePanel>
  </section>
</template>
<style scoped>
.result-head{display:flex;justify-content:space-between;gap:24px;padding:22px 24px 18px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.result-head h3{margin-top:12px;font-size:18px}
.result-head p{margin-top:8px;font-size:12px;color:var(--muted)}
.result-meta{display:flex;gap:22px;flex-wrap:wrap;margin:0}
.result-meta dt{font-size:10px;letter-spacing:.12em;color:var(--muted)}
.result-meta dd{margin:4px 0 0;font-size:12px}
.rec-list{list-style:none;margin:0;padding:8px 24px 24px;display:flex;flex-direction:column}
.rec-card{display:grid;grid-template-columns:54px 92px minmax(0,1fr);gap:18px;padding:18px 0;border-bottom:1px solid #31413e66;align-items:start}
.rec-card:last-child{border-bottom:0}
.rec-rank{font-family:Georgia,serif;font-size:26px;color:var(--accent);line-height:1;padding-top:4px}
.rec-poster{display:block;border-radius:6px;overflow:hidden;transition:border-color .18s}
.rec-poster .movie-poster{aspect-ratio:2/3;border-radius:6px}
.rec-poster:hover .movie-poster{border-color:var(--accent)}
.rec-body{min-width:0}
.rec-title{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.rec-title h4{margin:0;font-size:16px;font-weight:600;line-height:1.45}
.rec-title a:hover h4{color:var(--accent)}
.rec-year{font-size:11px;color:var(--muted);font-family:monospace}
.rec-genres{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.rec-genres span{font-size:10px;padding:2px 8px;border:1px solid var(--border);border-radius:99px;color:var(--muted)}
.rec-genres span.match{color:var(--accent);border-color:#dfb76c66;background:var(--accent-tint)}
.score-row{display:flex;align-items:center;gap:10px;margin-top:12px;font-size:11px;color:var(--muted)}
.score-track{flex:1;max-width:220px;height:4px;background:#31413e;border-radius:99px;overflow:hidden}
.score-track i{display:block;height:100%;background:linear-gradient(90deg,#8f7440,var(--accent));border-radius:99px}
.score-row strong{font-family:monospace;color:var(--text);font-weight:500}
.rec-why{margin-top:8px;font-size:11px;color:var(--accent)}
@media(max-width:780px){.rec-list{padding:4px 16px 16px}.rec-card{grid-template-columns:38px 72px minmax(0,1fr);gap:12px}.rec-rank{font-size:20px}.result-head{padding:18px 16px 14px}.result-meta{gap:14px}}
@media(max-width:540px){.rec-card{grid-template-columns:32px minmax(0,1fr)}.rec-poster{display:none}.rec-rank{font-size:18px}.rec-title h4{font-size:14px}}
</style>
