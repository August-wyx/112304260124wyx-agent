<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import http, { ApiError } from '../api'
import { useRemote } from '../composables/useRemote'
import type { Algorithm, HistoryUser, Movie, Page } from '../types'
import StatePanel from '../components/StatePanel.vue'
import PageNav from '../components/PageNav.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'

const route = useRoute(), router = useRouter(), auth = useAuth()
const source = ref('ml'), algorithm = ref('popular'), selected = ref('')
const userPage = ref(1), users = useRemote<Page<HistoryUser>>(), ratings = useRemote<Page<Movie>>()
const profileRatings = useRemote<Page<Movie>>()
const appRatings = useRemote<Page<Movie>>(), appFavorites = useRemote<Page<Movie>>()
const ratingPage = ref(1), available = ref<Algorithm[]>([]), registryError = ref<unknown>(null)
const evaluationError = ref<unknown>(null), evaluationPending = ref(false), evaluationMissing = ref(false)
const interests = ref<string[]>([]), genres = useRemote<{ items: string[] }>()

const algorithmNames: Record<string, string> = {
  content: '内容推荐', itemcf: '协同过滤', als: '矩阵分解', popular: '热门推荐', cold_start: '冷启动',
}
const subject = computed(() => source.value === 'ml' ? (selected.value ? `ml:${selected.value}` : '') : auth.account?.subject_key || '')
const endpoint = computed(() => {
  if (!subject.value) return null
  if (source.value === 'ml') return `/demo/history-users/${selected.value}/recommendations/${algorithm.value}`
  const base = `/me/recommendations/${algorithm.value}`
  return algorithm.value === 'cold_start' && interests.value.length
    ? `${base}?interests=${encodeURIComponent(interests.value.join(','))}`
    : base
})
const apiPath = computed(() => endpoint.value ? `/api/v1${endpoint.value}` : '')
const registered = computed(() => available.value.filter(item => item.status === 'registered').map(item => item.algorithm))
const appRatingTotal = computed(() => appRatings.data.value?.total ?? 0)
const appFavoriteTotal = computed(() => appFavorites.data.value?.total ?? 0)
const zeroBehaviour = computed(() => appRatingTotal.value === 0 && appFavoriteTotal.value === 0)
const interestHint = computed(() => interests.value.length ? `已选择 ${interests.value.length} 个兴趣类型` : '未选择兴趣：回退到热门排行')

const gradeLabel = computed(() => algorithm.value === 'content' ? '内容匹配度' : algorithm.value === 'popular' ? '热度分' : algorithm.value === 'itemcf' ? '协同分' : algorithm.value === 'cold_start' ? '冷启动分' : '推荐分')
const notes: Record<string, string> = {
  content: '依据真实历史评分的类型偏好生成，已排除看过的电影。',
  popular: '由真实历史评分的数量与平均分共同排序，与当前观众行为无关。',
  itemcf: '由该观众评分过的电影在协同相似度图上扩散得到，已排除看过的电影。',
  cold_start: '',
  als: '该算法尚未接入。',
}
const resultNote = computed(() => algorithm.value === 'cold_start'
  ? (interests.value.length
    ? '冷启动基线叠加所选兴趣类型，按类型偏好重排。'
    : '账号零评分零收藏，直接回退到真实热门排行。')
  : notes[algorithm.value] || '')

const profileTotal = computed(() => profileRatings.data.value?.total || 0)
const profileAverage = computed(() => {
  const items = profileRatings.data.value?.items || []
  if (!items.length) return '—'
  const sum = items.reduce((total, movie) => total + Number(movie.rating || 0), 0)
  return (sum / items.length).toFixed(2)
})
const genreProfile = computed(() => {
  const weights = new Map<string, { weight: number; count: number }>()
  for (const movie of profileRatings.data.value?.items || []) {
    const weight = Number(movie.rating || 0) - 2.5
    for (const genre of movie.genres || []) {
      const current = weights.get(genre) || { weight: 0, count: 0 }
      weights.set(genre, { weight: current.weight + weight, count: current.count + 1 })
    }
  }
  const ranked = [...weights.entries()]
    .map(([name, value]) => ({ name, weight: value.weight, count: value.count }))
    .filter(item => item.weight > 0)
    .sort((left, right) => right.weight - left.weight || left.name.localeCompare(right.name))
    .slice(0, 5)
  const max = ranked.length ? ranked[0].weight : 1
  return ranked.map(item => ({ ...item, percent: Math.max(6, Math.round(item.weight / max * 100)) }))
})
const topGenreNames = computed(() => genreProfile.value.map(item => item.name))
const highlightGenres = computed(() => algorithm.value === 'cold_start' ? interests.value : topGenreNames.value)

function selectAlgorithm(value: string) {
  algorithm.value = value
  updateUrl()
}
function selectSource(value: string) {
  source.value = value
  updateUrl()
  if (value === 'app') void fetchAppActivity()
}
function toggleInterest(genre: string) {
  interests.value = interests.value.includes(genre)
    ? interests.value.filter(item => item !== genre)
    : [...interests.value, genre].slice(0, 8)
}
function updateUrl() {
  void router.replace({ path: '/experiments', query: { source: source.value, algorithm: algorithm.value, ...(selected.value ? { user: selected.value } : {}) } })
}
async function fetchUsers(page = userPage.value) {
  userPage.value = page
  await users.load(async () => (await http.get<Page<HistoryUser>>('/demo/history-users', { params: { page, per_page: 20 } })).data)
}
function fetchRatings() {
  if (source.value !== 'ml' || !selected.value) return
  return ratings.load(async () => (await http.get<Page<Movie>>(`/demo/history-users/${encodeURIComponent(selected.value)}/ratings`, { params: { page: ratingPage.value, per_page: 10 } })).data)
}
function fetchProfile() {
  if (source.value !== 'ml' || !selected.value) return
  return profileRatings.load(async () => (await http.get<Page<Movie>>(`/demo/history-users/${encodeURIComponent(selected.value)}/ratings`, { params: { page: 1, per_page: 50 } })).data)
}
function fetchAppActivity() {
  if (!auth.account) return
  void appRatings.load(async () => (await http.get<Page<Movie>>('/me/ratings', { params: { page: 1, per_page: 1 } })).data)
  void appFavorites.load(async () => (await http.get<Page<Movie>>('/me/favorites', { params: { page: 1, per_page: 1 } })).data)
}
function fetchGenres() {
  if (genres.data.value) return
  void genres.load(async () => (await http.get<{ items: string[] }>('/genres')).data)
}
async function fetchRegistry() {
  try { available.value = (await http.get<{ items: Algorithm[] }>('/experiments/algorithms')).data.items; registryError.value = null }
  catch (e) { registryError.value = e }
}
async function fetchEvaluation() {
  evaluationPending.value = true; evaluationError.value = null; evaluationMissing.value = false
  try { await http.get('/experiments/evaluations') }
  catch (e) { if (e instanceof ApiError && e.status === 501 && e.code === 'EVALUATION_NOT_IMPLEMENTED') evaluationMissing.value = true; else evaluationError.value = e }
  finally { evaluationPending.value = false }
}
watch(() => route.query, () => {
  source.value = route.query.source === 'app' ? 'app' : 'ml'
  algorithm.value = typeof route.query.algorithm === 'string' && /^[a-z_]+$/.test(route.query.algorithm) ? route.query.algorithm : 'popular'
  selected.value = typeof route.query.user === 'string' && /^[1-9][0-9]*$/.test(route.query.user) ? route.query.user : ''
}, { immediate: true })
watch(() => [selected.value, source.value], () => {
  ratingPage.value = 1
  void fetchRatings()
  void fetchProfile()
  if (source.value === 'app') void fetchAppActivity()
})
watch(() => auth.account?.account_id, () => { if (source.value === 'app') void fetchAppActivity() }, { immediate: true })
watch(() => algorithm.value, value => { if (value === 'cold_start') fetchGenres() })
void fetchUsers(); void fetchRegistry(); void fetchEvaluation(); void fetchRatings(); void fetchProfile(); void fetchAppActivity(); fetchGenres()
</script>
<template>
  <div class="page">
    <div class="lab-hero">
      <div class="lab-hero-copy">
        <p class="eyebrow">RECOMMENDATION LAB · MULTI-ENGINE</p>
        <h1>推荐实验室<span class="heading-dot">.</span></h1>
        <p>热门、冷启动与协同过滤共用同一套真实数据与接口契约，切换算法即可对比不同推荐逻辑。</p>
      </div>
      <div class="lab-hero-badges">
        <div><span>当前算法</span><strong>{{ algorithmNames[algorithm] || algorithm }}</strong><small>{{ algorithm }}</small></div>
        <div><span>数据</span><strong>Business</strong><small>history_ratings</small></div>
        <div><span>已接入</span><strong>{{ registered.length }} / {{ available.length || 5 }}</strong><small>registry</small></div>
      </div>
    </div>

    <div class="lab-notice">
      <span class="status-pill">课程实验</span>
      <p>历史用户只读；注册账号与匿名用户相互隔离。推荐结果来自真实算法运行，不使用静态或预置列表。</p>
    </div>

    <div class="lab-layout">
      <aside class="lab-controls">
        <h2>实验设置</h2>
        <label for="subject-source">用户来源</label>
        <el-select id="subject-source" v-model="source" @change="selectSource">
          <el-option label="MovieLens 历史用户（只读）" value="ml" />
          <el-option label="当前注册账号" value="app" />
        </el-select>

        <template v-if="source === 'ml'">
          <label for="history-user">选择历史用户</label>
          <div class="quick-users">
            <span>课堂样例</span>
            <button type="button" :class="{ active: selected === '14' }" @click="selected = '14'; updateUrl()">ml14</button>
            <button type="button" :class="{ active: selected === '55' }" @click="selected = '55'; updateUrl()">ml55</button>
          </div>
          <el-select id="history-user" v-model="selected" placeholder="请从真实用户列表选择" @change="updateUrl">
            <el-option v-for="u in users.data.value?.items" :key="u.ml_user_id" :label="`${u.subject_key} · ${u.evaluation_role}`" :value="u.ml_user_id" />
          </el-select>
          <StatePanel v-if="users.error.value" :error="users.error.value" @retry="fetchUsers()" />
          <p v-if="users.loading.value" class="muted" role="status">正在加载用户…</p>
          <div class="user-pager">
            <el-button :disabled="userPage === 1 || users.loading.value" @click="fetchUsers(userPage - 1)">上一组</el-button>
            <span>{{ userPage }} / {{ Math.ceil((users.data.value?.total || 0) / 20) || 1 }}</span>
            <el-button :disabled="!users.data.value || userPage * 20 >= users.data.value.total || users.loading.value" @click="fetchUsers(userPage + 1)">下一组</el-button>
          </div>
          <p class="form-hint">按原始用户ID分页，支持全部课堂历史用户。</p>
        </template>
        <div v-else class="current-subject">
          <p>{{ auth.account?.login_name || '请先登录注册账号' }}</p>
          <span>{{ auth.account?.subject_key || '尚未登录' }}</span>
          <div v-if="auth.account" class="app-behaviour">
            <div><strong>{{ appRatingTotal }}</strong><span>评分</span></div>
            <div><strong>{{ appFavoriteTotal }}</strong><span>收藏</span></div>
            <div class="behaviour-state" :class="{ zero: zeroBehaviour }">{{ zeroBehaviour ? '零行为 · 冷启动' : '已有行为' }}</div>
          </div>
          <RouterLink v-if="!auth.account" to="/login" class="text-link">前往登录 →</RouterLink>
        </div>

        <label>推荐算法</label>
        <div class="algorithm-cards" role="listbox" aria-label="推荐算法">
          <button v-for="a in available" :key="a.algorithm" type="button" role="option"
            :aria-selected="algorithm === a.algorithm" :class="['algorithm-card', { active: algorithm === a.algorithm }]"
            @click="selectAlgorithm(a.algorithm)">
            <span class="algorithm-name">{{ algorithmNames[a.algorithm] || a.algorithm }}</span>
            <span class="algorithm-code">{{ a.algorithm }}</span>
            <span class="algorithm-state" :class="{ ready: a.status === 'registered' }">{{ a.status === 'registered' ? '已接入' : '未实现' }}</span>
          </button>
        </div>
        <StatePanel v-if="registryError" :error="registryError" @retry="fetchRegistry" />

        <section v-if="algorithm === 'cold_start' && source === 'app'" class="interest-panel">
          <div class="section-top"><h3>兴趣类型（选做）</h3><span class="small-label">COLD START</span></div>
          <p class="form-hint">{{ interestHint }}，最多 8 个。</p>
          <StatePanel :loading="genres.loading.value" :error="genres.error.value" @retry="fetchGenres">
            <div class="genre-chips">
              <button v-for="genre in genres.data.value?.items || []" :key="genre" type="button"
                :class="{ active: interests.includes(genre) }" @click="toggleInterest(genre)">{{ genre }}</button>
            </div>
          </StatePanel>
        </section>

        <div class="model-info">
          <span>当前对象</span><strong>{{ subject || '未选择' }}</strong>
          <span>推荐算法</span><strong>{{ algorithmNames[algorithm] || algorithm }} · {{ algorithm }}</strong>
          <span>接口路径</span><strong class="mono">{{ apiPath || '选择用户后显示' }}</strong>
          <span>运行模式</span><strong>business · 只读实验入口</strong>
          <span>历史来源</span><strong>business / history_ratings</strong>
        </div>
      </aside>

      <div class="lab-results">
        <section v-if="source === 'ml' && selected" class="profile-panel">
          <div class="section-top">
            <h2>观众内容画像</h2>
            <span class="small-label">REAL HISTORY · {{ subject }}</span>
          </div>
          <StatePanel :loading="profileRatings.loading.value" :error="profileRatings.error.value"
            :empty="!!profileRatings.data.value && !profileRatings.data.value.items.length"
            title="这位观众还没有历史评分" description="没有真实历史就无法形成内容画像，推荐结果将为空。" @retry="fetchProfile">
            <div class="profile-body">
              <div class="profile-stats">
                <div><strong>{{ profileTotal }}</strong><span>条历史评分</span></div>
                <div><strong>{{ profileAverage }}</strong><span>平均评分</span></div>
                <div><strong>{{ genreProfile.length }}</strong><span>偏好类型</span></div>
              </div>
              <div class="genre-profile">
                <div v-for="genre in genreProfile" :key="genre.name" class="genre-line">
                  <span>{{ genre.name }}</span>
                  <div class="genre-track"><i :style="{ width: genre.percent + '%' }" /></div>
                  <small>{{ genre.count }} 部</small>
                </div>
              </div>
            </div>
          </StatePanel>
        </section>

        <AlgorithmPanel :key="`${subject}-${algorithm}`" :label="`${algorithmNames[algorithm] || algorithm} · 推荐结果`"
          :endpoint="endpoint" :algorithm="algorithm" :subject="subject" :profile-genres="highlightGenres"
          :score-label="gradeLabel" :note="resultNote" :interests="interests"
          :empty-subject="source === 'ml' ? '请选择历史用户' : '登录后体验'" />

        <section v-if="source === 'ml'" class="history-panel">
          <div class="section-top">
            <h2>历史评分</h2>
            <span class="status-pill">{{ subject || '未选择用户' }} · 只读</span>
          </div>
          <StatePanel :loading="ratings.loading.value" :error="ratings.error.value" :empty="!selected || !!ratings.data.value && !ratings.data.value.items.length"
            title="选择一位历史观众" description="这里将显示真实历史评分，不提供修改入口。" @retry="fetchRatings">
            <div class="table-scroll">
              <el-table :data="ratings.data.value?.items || []" aria-label="历史用户只读评分表">
                <el-table-column label="电影" min-width="200">
                  <template #default="scope"><RouterLink :to="`/movies/${scope.row.movie_id}`" class="text-link">{{ scope.row.movielens_title }}</RouterLink></template>
                </el-table-column>
                <el-table-column label="类型" min-width="150">
                  <template #default="scope">{{ (scope.row.genres || []).join(' / ') || '未收录' }}</template>
                </el-table-column>
                <el-table-column prop="movie_id" label="电影ID" width="100" />
                <el-table-column prop="rating" label="历史评分" width="100" />
              </el-table>
            </div>
            <PageNav :page="ratingPage" :size="10" :total="ratings.data.value?.total || 0" @change="ratingPage = $event; fetchRatings()" />
          </StatePanel>
        </section>

        <section class="evaluation-panel">
          <div class="section-top"><h2>离线评价</h2><span class="small-label">PRECISION@10 / RECALL@10</span></div>
          <StatePanel :loading="evaluationPending" :error="evaluationError" @retry="fetchEvaluation">
            <div class="evaluation-empty">
              <span class="status-pill">{{ evaluationMissing ? '尚未实现' : '等待接入' }}</span>
              <p>暂无评价指标，等待离线评价程序接入。</p>
              <small>训练仅允许使用固定 train；此页面不连接 evaluation 数据库。</small>
            </div>
          </StatePanel>
        </section>
      </div>
    </div>
  </div>
</template>
<style scoped>
.lab-hero{display:flex;justify-content:space-between;align-items:end;gap:32px;border:1px solid var(--border);border-radius:12px;padding:34px 36px;background:linear-gradient(115deg,#192b2b,#182424 68%,#1d2b29);margin-bottom:24px;flex-wrap:wrap}
.lab-hero h1{margin:0 0 12px;font-size:clamp(30px,3.2vw,42px)}
.lab-hero-copy>p:last-child{color:var(--muted);font-size:14px;max-width:46em}
.lab-hero-badges{display:flex;gap:14px;flex-wrap:wrap}
.lab-hero-badges>div{border:1px solid #dfb76c2e;background:#dfb76c0a;border-radius:8px;padding:12px 16px;min-width:120px}
.lab-hero-badges span{display:block;font-size:10px;letter-spacing:.14em;color:var(--muted)}
.lab-hero-badges strong{display:block;font-size:16px;color:var(--accent);margin-top:4px}
.lab-hero-badges small{display:block;font-size:10px;color:var(--muted);margin-top:2px}
.quick-users{display:flex;align-items:center;gap:8px;margin:0 0 10px;font-size:11px;color:var(--muted)}
.quick-users button{border:1px solid var(--border);background:transparent;color:var(--text);border-radius:99px;padding:3px 12px;font-size:11px;transition:border-color .18s,color .18s}
.quick-users button:hover,.quick-users button.active{border-color:var(--accent);color:var(--accent)}
.algorithm-cards{display:flex;flex-direction:column;gap:8px}
.algorithm-card{display:grid;grid-template-columns:1fr auto;gap:2px 10px;text-align:left;border:1px solid var(--border);background:#182322;border-radius:7px;padding:10px 12px;color:var(--text);transition:border-color .18s,background .18s}
.algorithm-card:hover{border-color:#dfb76c66}
.algorithm-card.active{border-color:var(--accent);background:var(--accent-tint)}
.algorithm-name{font-size:13px;font-weight:600}
.algorithm-code{grid-column:1;font-size:10px;font-family:monospace;color:var(--muted)}
.algorithm-state{grid-column:2;grid-row:1/3;align-self:center;font-size:10px;color:var(--muted);border:1px solid var(--border);border-radius:99px;padding:2px 8px;white-space:nowrap}
.algorithm-state.ready{color:var(--accent);border-color:#dfb76c55}
.model-info .mono{font-family:monospace;font-size:11px;line-height:1.5}
.app-behaviour{display:flex;align-items:center;gap:14px;margin-top:10px;flex-wrap:wrap}
.app-behaviour div{display:flex;align-items:baseline;gap:5px}
.app-behaviour strong{font-family:Georgia,serif;font-size:20px;color:var(--accent)}
.app-behaviour span{font-size:10px;color:var(--muted)}
.app-behaviour .behaviour-state{font-size:10px;border:1px solid var(--border);border-radius:99px;padding:3px 10px;color:var(--muted)}
.app-behaviour .behaviour-state.zero{color:var(--accent);border-color:#dfb76c66;background:var(--accent-tint)}
.interest-panel{border:1px solid var(--border);border-radius:8px;padding:14px 14px 16px;background:#182322;margin-top:4px}
.interest-panel h3{margin:0;font-size:13px}
.genre-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.genre-chips button{border:1px solid var(--border);background:transparent;color:var(--muted);border-radius:99px;padding:4px 10px;font-size:11px;transition:border-color .18s,color .18s}
.genre-chips button:hover{color:var(--text);border-color:#dfb76c66}
.genre-chips button.active{color:var(--accent);border-color:var(--accent);background:var(--accent-tint)}
.profile-panel{border:1px solid var(--border);background:var(--surface);border-radius:8px;overflow:hidden}
.profile-body{display:grid;grid-template-columns:200px minmax(0,1fr);gap:28px;padding:22px 24px}
.profile-stats{display:flex;flex-direction:column;gap:14px;border-right:1px solid var(--border);padding-right:22px}
.profile-stats strong{font-size:26px;font-family:Georgia,serif;color:var(--accent);line-height:1}
.profile-stats span{display:block;font-size:11px;color:var(--muted);margin-top:4px}
.genre-profile{display:flex;flex-direction:column;gap:9px;justify-content:center}
.genre-line{display:grid;grid-template-columns:76px minmax(0,1fr) 46px;align-items:center;gap:10px;font-size:12px}
.genre-line>span{color:var(--text)}
.genre-line small{color:var(--muted);font-size:10px;text-align:right}
.genre-track{height:5px;background:#31413e;border-radius:99px;overflow:hidden}
.genre-track i{display:block;height:100%;background:linear-gradient(90deg,#6f5a33,var(--accent));border-radius:99px}
@media(max-width:1100px){.lab-hero{padding:28px}.profile-body{grid-template-columns:160px minmax(0,1fr);gap:20px}.profile-stats{padding-right:16px}}
@media(max-width:780px){.lab-hero{align-items:start}.lab-hero-badges{width:100%}.profile-body{grid-template-columns:1fr}.profile-stats{flex-direction:row;border-right:0;border-bottom:1px solid var(--border);padding:0 0 16px;gap:32px}}
</style>
