<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Star, Back } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http, { errorMessage } from '../api'
import { useAuth } from '../stores/auth'
import { useRemote } from '../composables/useRemote'
import type { Movie, Page } from '../types'
import { genreLabel } from '../genres'
import MoviePoster from '../components/MoviePoster.vue'
import StatePanel from '../components/StatePanel.vue'
const route = useRoute(), router = useRouter(), auth = useAuth()
const { data: movie, error, loading, load } = useRemote<Movie>()
const score = ref<number>(0), savedScore = ref<string | null>(null), favorited = ref(false)
const activityLoading = ref(false), activityError = ref<unknown>(null), saving = ref(false)
let activityRun = 0
const id = computed(() => String(route.params.id))
const displayTitle = computed(() => movie.value?.title_zh || movie.value?.movielens_title || '')
const backdropStyle = computed<Record<string, string>>(() => ({
  '--backdrop': movie.value?.movie_id ? `url('/posters/${movie.value.movie_id}.jpg')` : 'none',
}))
const facts = computed(() => {
  const film = movie.value
  if (!film) return []
  return [
    { label: '上映年份', value: film.release_year || '暂未收录' },
    { label: '上映日期', value: film.release_date || '暂未收录' },
    { label: '片长', value: film.runtime_minutes ? `${film.runtime_minutes} 分钟` : '暂未收录' },
    { label: '原始语言', value: film.original_language || '暂未收录' },
  ]
})
function fetchMovie() { return load(async () => (await http.get<Movie>(`/movies/${encodeURIComponent(id.value)}`)).data) }
async function retryMovie() { await fetchMovie(); await fetchActivity() }
function people(value: unknown[] | null | undefined) { if (!value?.length) return '暂未收录'; return value.map(p => typeof p === 'string' ? p : (p && typeof p === 'object' && 'name' in p ? String(p.name) : '')).filter(Boolean).join(' / ') || '暂未收录' }
// There is no single-movie favorite endpoint: inspect the real paged list, do not invent one.
async function fetchActivity() {
  const seq = ++activityRun, currentId = id.value
  savedScore.value = null; score.value = 0; favorited.value = false; activityError.value = null; activityLoading.value = false
  if (!auth.account || !movie.value) return
  activityLoading.value = true
  try {
    const rating = (await http.get<{rating:string|null}>(`/me/ratings/${currentId}`)).data.rating
    let found = false, page = 1
    while (seq === activityRun) {
      const list = (await http.get<Page<Movie>>('/me/favorites', { params: { page, per_page: 100 } })).data
      found = list.items.some(item => item.movie_id === currentId)
      if (found || page * 100 >= list.total) break
      page++
    }
    if (seq === activityRun) { savedScore.value = rating; score.value = rating ? Number(rating) : 0; favorited.value = found }
  } catch (e) { if (seq === activityRun) activityError.value = e }
  finally { if (seq === activityRun) activityLoading.value = false }
}
async function rate() {
  if (!score.value) return
  saving.value = true; activityError.value = null
  try { const result = (await http.put<{rating:string}>(`/me/ratings/${id.value}`, { rating: score.value })).data; savedScore.value = result.rating; ElMessage.success('评分已保存') }
  catch (e) { activityError.value = e; ElMessage.error(errorMessage(e)) }
  finally { saving.value = false }
}
async function toggleFavorite() {
  saving.value = true; activityError.value = null
  try { if (favorited.value) await http.delete(`/me/favorites/${id.value}`); else await http.put(`/me/favorites/${id.value}`); favorited.value = !favorited.value; ElMessage.success(favorited.value ? '已加入收藏' : '已取消收藏') }
  catch (e) { activityError.value = e; ElMessage.error(errorMessage(e)) }
  finally { saving.value = false }
}
watch(id, async () => { await fetchMovie(); await fetchActivity() }, { immediate: true })
watch(() => auth.account?.account_id, fetchActivity)
</script>
<template>
  <div class="page detail-page">
    <div class="detail-topbar"><RouterLink to="/movies" class="back-pill"><el-icon aria-hidden="true"><Back /></el-icon> 返回电影库</RouterLink><span v-if="movie" class="archive-code">MOVIELENS / NO.{{ movie.movie_id }}</span></div>
    <StatePanel :loading="loading" :error="error" @retry="retryMovie">
      <article v-if="movie" class="dossier">
        <header class="dossier-hero" :style="backdropStyle">
          <span class="dossier-scrim" aria-hidden="true" />
          <div class="dossier-poster"><MoviePoster :path="movie.poster_path" :title="movie.movielens_title" :movie-id="movie.movie_id" :year="movie.release_year" :genres="movie.genres" /></div>
          <div class="dossier-head">
            <p class="eyebrow">FILM DOSSIER · 影片档案</p>
            <h1>{{ displayTitle }}</h1>
            <p v-if="movie.title_zh" class="original-title">{{ movie.movielens_title }}</p>
            <div class="dossier-chips">
              <span v-for="genre in movie.genres" :key="genre" class="chip accent">{{ genreLabel(genre) }}</span>
              <span class="chip">{{ movie.release_year || '年份未收录' }}</span>
              <span v-if="movie.runtime_minutes" class="chip">{{ movie.runtime_minutes }} 分钟</span>
              <span v-if="movie.original_language" class="chip">{{ movie.original_language }}</span>
            </div>
            <p class="dossier-lede">{{ movie.overview || '剧情简介暂未收录。你仍然可以为这部电影评分或加入收藏。' }}</p>
            <div class="dossier-actions">
              <a class="button primary" href="#journal">留下评分</a>
              <el-button v-if="auth.account" :icon="Star" :disabled="saving" :aria-pressed="favorited" @click="toggleFavorite">{{ favorited ? '已收藏' : '收藏电影' }}</el-button>
              <RouterLink v-else class="button subtle" :to="{ path: '/login', query: { redirect: route.fullPath } }">登录后记录</RouterLink>
            </div>
          </div>
        </header>

        <div class="dossier-body">
          <section class="fact-card">
            <div class="block-head"><h2>影片资料</h2><span class="small-label">FILM FACTS</span></div>
            <dl class="fact-grid">
              <div v-for="fact in facts" :key="fact.label"><dt>{{ fact.label }}</dt><dd>{{ fact.value }}</dd></div>
              <div class="wide"><dt>导演</dt><dd>{{ people(movie.directors) }}</dd></div>
              <div class="wide"><dt>主要演员</dt><dd>{{ people(movie.cast_top10) }}</dd></div>
            </dl>
            <div class="synopsis"><h3>关于这部电影</h3><p>{{ movie.overview || '剧情简介暂未收录。你仍然可以为这部电影评分或加入收藏。' }}</p></div>
          </section>

          <section id="journal" class="journal-card" aria-label="我的电影记录">
            <div class="block-head"><div><p class="eyebrow">MY FILM JOURNAL</p><h2>留下你的观影印记</h2></div><span class="status-pill">{{ auth.account ? auth.account.subject_key : '尚未登录' }}</span></div>
            <template v-if="auth.account">
              <StatePanel :loading="activityLoading" :error="activityError" @retry="fetchActivity">
                <div class="rating-block">
                  <el-rate v-model="score" allow-half :disabled="saving" aria-label="我的评分" />
                  <strong class="rating-value">{{ score ? score.toFixed(1) : '—' }}<small> / 5.0</small></strong>
                </div>
                <p class="rating-state">{{ savedScore ? `已记录 ${savedScore} 分` : '还没有评分，点击星星留下第一印象。' }}</p>
                <div class="rating-actions">
                  <el-button type="primary" :disabled="!score || saving" :loading="saving" @click="rate">{{ savedScore ? '更新评分' : '保存评分' }}</el-button>
                  <el-button :icon="Star" :disabled="saving" :aria-pressed="favorited" @click="toggleFavorite">{{ favorited ? '取消收藏' : '收藏电影' }}</el-button>
                </div>
                <p class="form-hint">0.5—5.0 分，半星步长。评分只属于当前注册账号。</p>
              </StatePanel>
            </template>
            <div v-else class="journal-empty"><p>登录后记录评分，收藏想看的电影。</p><el-button type="primary" @click="router.push({ path: '/login', query: { redirect: route.fullPath } })">登录后记录</el-button></div>
          </section>
        </div>
      </article>
    </StatePanel>
  </div>
</template>
<style scoped>
.detail-page{padding-top:28px}
.detail-topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px;flex-wrap:wrap}
.back-pill{display:inline-flex;align-items:center;gap:8px;min-height:38px;padding:0 15px;border:1px solid var(--border);border-radius:999px;color:var(--muted);font-size:12px;transition:border-color .18s,color .18s}
.back-pill:hover{border-color:var(--accent);color:var(--accent)}
.archive-code{font-family:monospace;font-size:10px;letter-spacing:.16em;color:var(--muted)}
.dossier{display:flex;flex-direction:column;gap:26px}
.dossier-hero{position:relative;display:grid;grid-template-columns:250px minmax(0,1fr);gap:40px;padding:38px;border:1px solid var(--border);border-radius:18px;overflow:hidden;background:linear-gradient(120deg,#141b26,#10151e)}
.dossier-hero::before{content:'';position:absolute;inset:0;background-image:var(--backdrop);background-size:cover;background-position:center 22%;opacity:.2;filter:saturate(.9)}
.dossier-scrim{position:absolute;inset:0;background:linear-gradient(100deg,#0c0f15f2 18%,#0c0f15cc 46%,#0c0f1580 100%)}
.dossier-poster{position:relative;z-index:1;display:flex;align-items:flex-start}
.dossier-poster :deep(.movie-poster){box-shadow:0 34px 60px #00000080}
.dossier-head{position:relative;z-index:1;display:flex;flex-direction:column;justify-content:center;min-width:0}
.dossier-head h1{font-family:var(--font-display);font-size:clamp(30px,3.4vw,46px);line-height:1.28;margin:0 0 8px;overflow-wrap:anywhere}
.original-title{color:var(--muted);font-size:13px;letter-spacing:.02em}
.dossier-chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px}
.chip{font-size:11px;padding:4px 11px;border-radius:999px;border:1px solid var(--border);color:var(--muted);background:#ffffff06}
.chip.accent{color:var(--accent);border-color:#f06a5055;background:var(--accent-tint)}
.dossier-lede{color:var(--muted);font-size:14px;line-height:1.9;margin-top:20px;max-width:56em;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.dossier-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:24px}
.dossier-body{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.85fr);gap:24px;align-items:start}
.fact-card,.journal-card{border:1px solid var(--border);background:var(--surface);border-radius:14px;padding:26px}
.block-head{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.block-head h2{font-size:19px;font-family:var(--font-display)}
.block-head .eyebrow{margin:0}
.fact-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0}
.fact-grid>div{border:1px solid var(--border);border-radius:10px;padding:13px 15px;background:#ffffff03}
.fact-grid dt{font-size:10px;letter-spacing:.14em;color:var(--muted)}
.fact-grid dd{margin:6px 0 0;font-size:13px;line-height:1.6;color:var(--text)}
.fact-grid .wide{grid-column:1/-1}
.synopsis{margin-top:24px;padding-top:22px;border-top:1px solid var(--border)}
.synopsis h3{font-size:15px;margin-bottom:10px}
.synopsis p{color:var(--muted);font-size:13.5px;line-height:1.9}
.journal-card{position:sticky;top:104px}
.rating-block{display:flex;align-items:center;justify-content:space-between;gap:16px;border:1px solid var(--border);border-radius:12px;padding:18px;background:#ffffff03}
.rating-block :deep(.el-rate){height:34px}
.rating-block :deep(.el-rate__icon){font-size:26px;margin-right:6px}
.rating-value{font-family:Georgia,serif;font-size:24px;color:var(--accent);white-space:nowrap}
.rating-value small{font-size:11px;color:var(--muted);font-family:inherit}
.rating-state{margin-top:12px;font-size:12px;color:var(--muted)}
.rating-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
.rating-actions .el-button+.el-button{margin-left:0}
.journal-empty{display:flex;flex-direction:column;align-items:flex-start;gap:14px;color:var(--muted);font-size:13px}
.journal-card :deep(.state-panel){border:0;background:transparent;padding:6px 0;min-height:0;align-items:stretch;text-align:left}
@media(max-width:1100px){.dossier-hero{grid-template-columns:210px minmax(0,1fr);gap:28px;padding:28px}.dossier-body{grid-template-columns:minmax(0,1fr)}.journal-card{position:static}}
@media(max-width:780px){.dossier-hero{grid-template-columns:1fr;padding:24px;gap:20px}.dossier-poster{width:170px}.dossier-lede{display:block}.fact-card,.journal-card{padding:20px}.detail-page{padding-top:20px}}
@media(max-width:540px){.dossier-hero{padding:18px;border-radius:14px}.dossier-poster{width:145px}.fact-grid{grid-template-columns:1fr}.fact-grid .wide{grid-column:auto}.dossier-head h1{font-size:27px}.dossier-chips{gap:6px;margin-top:14px}.dossier-actions{gap:8px;margin-top:18px}.rating-block{flex-direction:column;align-items:flex-start;gap:8px}}
</style>
