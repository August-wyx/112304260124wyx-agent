﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { Connection, ChatDotRound, Loading } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import MoviePoster from './MoviePoster.vue'
import { genreLabel } from '../genres'
import type { AlgorithmResult, Movie } from '../types'

const props = withDefaults(defineProps<{
  endpoint: string | null
  label: string
  algorithm?: string
  subject?: string
  profileGenres?: string[]
  emptySubject?: string
  scoreLabel?: string
  note?: string
  interests?: string[]
}>(), {
  algorithm: '', subject: '', profileGenres: () => [], emptySubject: '登录后体验',
  scoreLabel: '推荐分', note: '', interests: () => [],
})

const loading = ref(false), error = ref<unknown>(null), unavailable = ref(false)
const result = ref<AlgorithmResult | null>(null)
const movies = ref<Record<string, Movie>>({})
const explainData = ref<{ items: any[]; algorithm: string; model_version: string } | null>(null)
const explainLoading = ref(false)
const explainError = ref(false)
const showExplain = ref(false)
let run = 0
onScopeDispose(() => { run++ })

const algorithmNames: Record<string, string> = {
  content: '内容推荐', itemcf: '协同过滤', als: '矩阵分解', popular: '热门推荐', cold_start: '冷启动',
}
const algorithmLabel = computed(() => algorithmNames[props.algorithm] ? `${algorithmNames[props.algorithm]} · ${props.algorithm}` : props.algorithm)
const engineLabels: Record<string, string> = {
  content: 'CONTENT-BASED ENGINE', popular: 'POPULARITY ENGINE', als: 'MATRIX FACTORIZATION',
  itemcf: 'ITEM-BASED COLLABORATIVE FILTERING', cold_start: 'COLD-START ENGINE',
}
const engineLabel = computed(() => engineLabels[props.algorithm] || 'RECOMMENDATION ENGINE')
const highlightEnabled = computed(() => ['content', 'cold_start'].includes(props.algorithm))
const emptyTexts: Record<string, string> = {
  itemcf: '这位观众还没有正评分的电影，ItemCF 无法形成协同信号。',
  cold_start: '当前没有可用候选电影。',
  popular: '当前没有可用评分统计。',
  content: '这位观众的历史不足以形成内容画像，本次没有推荐结果。',
}
const emptyResultText = computed(() => emptyTexts[props.algorithm] || '本次没有推荐结果。')

const rows = computed(() => (result.value?.items || []).map(item => {
  const movie = movies.value[item.movie_id] || null
  return {
    ...item,
    movie,
    percent: scorePercent(item.score),
    matched: matchedGenres(movie?.genres || []),
    genres: (movie?.genres || []).map(name => ({ name, label: genreLabel(name), match: matchedGenres([name]).length > 0 })),
  }
}))
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

const explainEndpoint = computed(() => {
  if (!props.endpoint) return null
  // endpoint is like /demo/history-users/14/recommendations/itemcf or /me/recommendations/itemcf
  return `${props.endpoint}/explain`
})

const explainRows = computed(() => explainData.value?.items || [])

async function openExplain() {
  if (!explainEndpoint.value) return
  showExplain.value = true
  explainLoading.value = true
  explainError.value = false
  try {
    const response = await http.get(explainEndpoint.value, { params: { ai: true }, timeout: 60000 })
    explainData.value = response.data as any
  } catch (e) {
    explainError.value = true
    explainData.value = { items: [], algorithm: props.algorithm, model_version: '' }
  } finally {
    explainLoading.value = false
  }
}

function evidencePreview(evidence: any): string {
  if (!evidence) return ''
  if (evidence.similarity !== undefined) return `相似度 ${(evidence.similarity * 100).toFixed(0)}%`
  if (evidence.cosine_fit !== undefined) return `匹配度 ${(evidence.cosine_fit * 100).toFixed(0)}%`
  if (evidence.rating_count !== undefined) return `${evidence.rating_count} 人评分 · 均分 ${evidence.avg_rating}`
  if (evidence.score !== undefined) return `匹配分 ${evidence.score}`
  if (evidence.watched_count !== undefined) return `历史 ${evidence.watched_count} 部`
  return ''
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
      <span class="small-label">{{ engineLabel }}</span>
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
            <p v-if="!result.items.length">{{ emptyResultText }}</p>
            <p v-else>{{ note }}</p>
          </div>
          <dl class="result-meta">
            <div><dt>模型版本</dt><dd>{{ result.model_version }}</dd></div>
            <div><dt>运行模式</dt><dd>{{ result.runtime_mode }}</dd></div>
            <div v-if="algorithm === 'cold_start'"><dt>兴趣</dt><dd>{{ interests.length ? interests.map(genreLabel).join(' / ') : '未选择 · 热门回退' }}</dd></div>
            <div><dt>生成时间</dt><dd>{{ generated }}</dd></div>
          </dl>
          <button v-if="result.items.length" class="explain-launch" @click="openExplain" :disabled="explainLoading">
            <el-icon v-if="!explainLoading"><ChatDotRound /></el-icon>
            <el-icon v-else class="spin"><Loading /></el-icon>
            <span>{{ explainLoading ? '生成解释中…' : '为什么推荐' }}</span>
          </button>
        </header>
        <ol v-if="result.items.length" class="rec-list">
          <li v-for="row in rows" :key="row.movie_id" class="rec-card">
            <RouterLink class="rec-poster" :to="`/movies/${row.movie_id}`" :aria-label="`查看 ${row.movie?.movielens_title || row.movie_id} 详情`">
              <MoviePoster :path="row.movie?.poster_path" :title="row.movie?.movielens_title || `电影 ${row.movie_id}`"
                :movie-id="row.movie_id" :year="row.movie?.release_year" :genres="row.movie?.genres" />
              <span class="rec-rank">{{ String(row.rank).padStart(2, '0') }}</span>
            </RouterLink>
            <div class="rec-body">
              <div class="rec-title">
                <RouterLink :to="`/movies/${row.movie_id}`">
                  <h4>{{ row.movie?.title_zh || row.movie?.movielens_title || `电影 #${row.movie_id}` }}</h4>
                </RouterLink>
                <span class="rec-year">{{ row.movie?.release_year || '年份未收录' }}</span>
              </div>
              <div class="rec-genres">
                <span v-for="genre in row.genres" :key="genre.name" :class="{ match: highlightEnabled && genre.match }">{{ genre.label }}</span>
                <span v-if="!row.movie" class="rec-fallback">电影 #{{ row.movie_id }}</span>
              </div>
              <div class="score-row">
                <span class="score-label">{{ scoreLabel }}</span>
                <div class="score-track" role="img" :aria-label="`${scoreLabel} ${row.percent}%`"><i :style="{ width: row.percent + '%' }" /></div>
                <strong>{{ row.score === null ? '—' : row.score.toFixed(3) }}</strong>
              </div>
              <p v-if="highlightEnabled && row.matched.length" class="rec-why">
                {{ algorithm === 'cold_start' ? '命中所选兴趣' : '与观众偏好类型重合' }}：{{ row.matched.map(genreLabel).join(' / ') }}
              </p>
            </div>
            <RouterLink class="rec-more" :to="`/movies/${row.movie_id}`">详情<span aria-hidden="true">→</span></RouterLink>
          </li>
        </ol>
      </div>
    </StatePanel>

    <!-- Explanation Dialog -->
    <el-dialog v-model="showExplain" class="explain-dialog" width="640px" :close-on-click-modal="true"
      :show-close="true" align-center destroy-on-close>
      <template #header>
        <div class="explain-header">
          <span class="explain-title">为什么推荐这 {{ explainRows.length }} 部？</span>
          <span class="explain-sub">{{ explainData?.algorithm }} · {{ explainData?.model_version || '—' }}</span>
        </div>
      </template>
      <div class="explain-body" v-if="explainLoading">
        <div class="explain-loading"><el-icon class="spin"><Loading /></el-icon><span>正在为每部电影生成可核验的推荐理由…</span></div>
      </div>
      <div class="explain-body" v-else>
        <div v-if="explainError" class="explain-empty">解释暂不可用，请稍后重试。推荐列表不受影响。</div>
        <div v-else-if="!explainRows.length" class="explain-empty">当前没有解释数据。</div>
        <article v-for="item in explainRows" :key="item.movie_id" class="explain-item">
          <header class="explain-item-head">
            <span class="explain-rank">#{{ item.rank }}</span>
            <h4>{{ item.title }}</h4>
            <RouterLink class="explain-detail" :to="`/movies/${item.movie_id}`" @click="showExplain = false">详情 →</RouterLink>
          </header>
          <p class="explain-genres">{{ item.genres?.join(' / ') || '—' }}</p>
          <div v-if="item.ai_reason" class="explain-ai-block">
            <span class="ai-badge">AI 推荐理由</span>
            <p class="ai-reason-text">{{ item.ai_reason }}</p>
          </div>
          <ul class="explain-reasons">
            <li v-for="(reason, i) in item.reasons" :key="i" class="explain-reason">
              <span class="reason-type">{{ reason.type === 'itemcf_neighbor' ? '协同过滤依据' : reason.type === 'content_genre' ? '类型匹配依据' : reason.type === 'popularity' ? '热门依据' : reason.type === 'als_latent' ? '隐因子依据' : reason.type === 'coldstart_fallback' ? '冷启动回退' : '综合依据' }}</span>
              <span class="reason-text">{{ reason.text }}</span>
              <span class="reason-evidence" v-if="evidencePreview(reason.evidence)">{{ evidencePreview(reason.evidence) }}</span>
            </li>
          </ul>
        </article>
        <p class="explain-foot">每条理由附带原始证据，可回溯到模型工件或用户历史评分。AI 解释由 Doubao 大模型基于真实依据生成。</p>
      </div>
    </el-dialog>
  </section>
</template>
<style scoped>
.result-head{display:flex;justify-content:space-between;gap:24px;padding:22px 24px 20px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.result-head h3{margin-top:12px;font-family:var(--font-display);font-size:19px;letter-spacing:.01em}
.result-head p{margin-top:8px;font-size:12px;color:var(--muted)}
.result-meta{display:flex;gap:22px;flex-wrap:wrap;margin:0}
.result-meta dt{font-size:10px;letter-spacing:.14em;color:var(--muted)}
.result-meta dd{margin:4px 0 0;font-size:12px}
.rec-list{list-style:none;margin:0;padding:14px;display:flex;flex-direction:column;gap:10px}
.rec-card{display:grid;grid-template-columns:76px minmax(0,1fr) auto;gap:18px;align-items:center;padding:14px;border:1px solid var(--border);border-radius:10px;background:var(--surface-soft);transition:border-color .2s,transform .2s,background .2s}
.rec-card:hover{border-color:#f06a5059;background:#202a39;transform:translateX(4px)}
.rec-poster{position:relative;display:block;border-radius:8px;overflow:hidden;transition:box-shadow .2s}
.rec-poster:hover{box-shadow:0 8px 22px #00000059}
.rec-rank{position:absolute;left:6px;top:6px;z-index:2;font-family:var(--font-display);font-size:12px;line-height:1.5;letter-spacing:.04em;color:var(--gold);background:#0c0f15d9;border:1px solid #ffffff1f;border-radius:4px;padding:0 6px}
.rec-body{min-width:0}
.rec-title{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.rec-title h4{margin:0;font-family:var(--font-display);font-size:16px;font-weight:600;line-height:1.45;letter-spacing:.01em}
.rec-title a:hover h4{color:var(--accent)}
.rec-year{font-size:11px;color:var(--muted);font-family:monospace}
.rec-genres{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.rec-genres span{font-size:10px;padding:2px 9px;border:1px solid var(--border);border-radius:99px;color:var(--muted);background:#0c0f1566}
.rec-genres span.match{color:var(--accent);border-color:#f06a5066;background:var(--accent-tint)}
.rec-genres span.rec-fallback{color:var(--muted)}
.score-row{display:flex;align-items:center;gap:10px;margin-top:12px;font-size:11px;color:var(--muted)}
.score-label{white-space:nowrap;letter-spacing:.04em}
.score-track{flex:1;max-width:220px;height:4px;background:#2c3646;border-radius:99px;overflow:hidden}
.score-track i{display:block;height:100%;background:linear-gradient(90deg,var(--gold),var(--accent));border-radius:99px}
.score-row strong{font-family:monospace;color:var(--text);font-weight:500}
.rec-why{margin-top:8px;font-size:11px;color:var(--accent)}
.rec-more{align-self:center;display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);border:1px solid var(--border);border-radius:99px;padding:6px 13px;white-space:nowrap;transition:color .18s,border-color .18s,background .18s}
.rec-more:hover{color:var(--ink);border-color:var(--accent);background:var(--accent)}
.explain-launch{align-self:center;display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--gold);border:1px solid var(--gold);border-radius:99px;padding:7px 16px;background:transparent;cursor:pointer;transition:color .18s,background .18s,border-color .18s}
.explain-launch:hover{color:var(--ink);background:var(--gold);border-color:var(--gold)}
.explain-launch:disabled{opacity:.5;cursor:default}
.explain-launch .spin{animation:spin 1s linear infinite}
.explain-dialog :deep(.el-dialog){background:var(--surface);border:1px solid var(--border);border-radius:14px}
.explain-dialog :deep(.el-dialog__header){border-bottom:1px solid var(--border);padding:18px 22px;margin:0}
.explain-dialog :deep(.el-dialog__body){padding:0;max-height:72vh;overflow-y:auto}
.explain-header{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.explain-title{font-family:var(--font-display);font-size:18px;color:var(--text);letter-spacing:.01em}
.explain-sub{font-size:11px;color:var(--muted);font-family:monospace}
.explain-body{padding:22px}
.explain-loading{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:13px;justify-content:center;padding:40px}
.explain-loading .spin{font-size:20px;color:var(--accent);animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.explain-empty{text-align:center;color:var(--muted);padding:40px}
.explain-item{margin-bottom:22px;padding-bottom:22px;border-bottom:1px dashed var(--border)}
.explain-item:last-child{margin-bottom:0;padding-bottom:0;border-bottom:none}
.explain-item-head{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}
.explain-rank{font-family:var(--font-display);color:var(--gold);font-size:14px;font-weight:700}
.explain-item-head h4{margin:0;font-family:var(--font-display);font-size:16px;color:var(--text);font-weight:600;flex:1}
.explain-detail{font-size:11px;color:var(--accent);text-decoration:none;white-space:nowrap}
.explain-detail:hover{text-decoration:underline}
.explain-genres{font-size:11px;color:var(--muted);margin:0 0 10px}
.explain-reasons{list-style:none;margin:0;padding:0}
.explain-reason{display:grid;grid-template-columns:auto 1fr auto;gap:10px;padding:10px 12px;background:var(--surface-soft);border:1px solid var(--border);border-radius:8px;margin-bottom:8px;align-items:start}
.reason-type{font-size:10px;letter-spacing:.04em;color:var(--gold);font-family:monospace;white-space:nowrap;padding-top:2px}
.reason-text{font-size:13px;color:var(--text);line-height:1.65}
.reason-evidence{font-size:10px;color:var(--accent);font-family:monospace;white-space:nowrap;align-self:center;padding:3px 8px;border:1px solid var(--accent);border-radius:99px;background:var(--accent-tint)}
.explain-ai-block{background:linear-gradient(135deg,rgba(100,149,237,.08),rgba(147,112,219,.08));border:1px solid rgba(147,112,219,.3);border-radius:10px;padding:14px 16px;margin:8px 0 12px;position:relative}
.ai-badge{display:inline-block;font-size:10px;letter-spacing:.06em;color:#9370db;font-weight:600;font-family:monospace;padding:2px 8px;border-radius:99px;background:rgba(147,112,219,.12);border:1px solid rgba(147,112,219,.3);margin-bottom:8px}
.ai-reason-text{margin:0;font-size:14px;color:var(--text);line-height:1.7;font-weight:500}
.explain-foot{margin:18px 0 0;font-size:11px;color:var(--muted);text-align:center}
@media(max-width:780px){.rec-list{padding:10px}.rec-card{grid-template-columns:66px minmax(0,1fr);gap:13px;padding:12px}.rec-more{display:none}.result-head{padding:18px 16px 16px}.result-meta{gap:14px}}
@media(max-width:540px){.rec-card{grid-template-columns:58px minmax(0,1fr);gap:11px}.rec-title h4{font-size:14px}.score-track{max-width:none}.score-row{margin-top:9px}}
</style>
