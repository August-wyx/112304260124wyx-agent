<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowRight, Search, Reading, Star } from '@element-plus/icons-vue'
import http from '../api'
import { useAuth } from '../stores/auth'
import { useRemote } from '../composables/useRemote'
import type { Movie, Page } from '../types'
import MovieCard from '../components/MovieCard.vue'
import MoviePoster from '../components/MoviePoster.vue'
import StatePanel from '../components/StatePanel.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'
const auth = useAuth()
const { data, error, loading, load } = useRemote<Page<Movie>>()
// Preload a local poster image to decide whether the movie has a real cover.
function hasLocalPoster(movieId: number | string): Promise<boolean> {
  return new Promise(resolve => {
    const img = new Image()
    img.onload = () => resolve(true)
    img.onerror = () => resolve(false)
    img.src = `/posters/${movieId}.jpg`
  })
}
// Fetch a larger pool and keep only movies that actually have a poster image,
// so the hero carousel never falls back to the placeholder card.
const fetchMovies = () => load(async () => {
  const page = (await http.get<Page<Movie>>('/movies', { params: { per_page: 24 } })).data
  const checks = await Promise.all(page.items.map(m => hasLocalPoster(m.movie_id).then(ok => ({ m, ok }))))
  page.items = checks.filter(c => c.ok).map(c => c.m).slice(0, 8)
  page.total = page.items.length
  return page
})
const featured = computed(() => data.value?.items || [])
onMounted(fetchMovies)

// 实验五：登录用户按是否已有评分切换推荐策略
// 有评分 -> Content(内容画像) + ItemCF(协同过滤)；零评分新用户 -> Popular + ColdStart
const ratedCount = ref<number | null>(null)
watch(() => auth.account?.account_id, async (id) => {
  ratedCount.value = null
  if (!id) return
  try {
    const r = await http.get<Page<Movie>>('/me/ratings', { params: { page: 1, per_page: 1 } })
    ratedCount.value = r.data.total
  } catch { ratedCount.value = 0 }
}, { immediate: true })
const isNewUser = computed(() => auth.account !== null && ratedCount.value === 0)
const primaryPanel = computed(() => !auth.account
  ? { endpoint: null as string | null, algorithm: 'content', label: '为你推荐' }
  : isNewUser.value
    ? { endpoint: '/me/recommendations/popular' as string | null, algorithm: 'popular', label: '热门推荐' }
    : { endpoint: '/me/recommendations/content' as string | null, algorithm: 'content', label: '为你推荐' })
const secondaryPanel = computed(() => !auth.account
  ? { endpoint: null as string | null, algorithm: 'itemcf', label: '协同过滤推荐' }
  : isNewUser.value
    ? { endpoint: '/me/recommendations/cold_start' as string | null, algorithm: 'cold_start', label: '按兴趣推荐' }
    : { endpoint: '/me/recommendations/itemcf' as string | null, algorithm: 'itemcf', label: '协同过滤推荐' })
</script>
<template>
  <div class="page home-page">
    <section class="hero-stage">
      <div class="hero-copy">
        <p class="hero-kicker"><span class="kicker-dot" /> HUWEN CINEMA · 今日精选</p>
        <h1>让好电影，<br /><em>找到你。</em></h1>
        <p class="hero-description">从一部电影开始，发现自己的观影偏好。<br />探索真实片库，让每一次评分留下回响。</p>
        <div class="hero-actions"><RouterLink class="button primary" to="/movies">探索电影库 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink><RouterLink class="button subtle" to="/experiments">进入推荐实验室</RouterLink></div>
        <dl class="hero-stats">
          <div><dt>真实片源</dt><dd>{{ data?.total?.toLocaleString() || '—' }}</dd></div>
          <div><dt>推荐算法</dt><dd>5 <small>种</small></dd></div>
          <div><dt>评价口径</dt><dd>Top-10</dd></div>
        </dl>
      </div>
      <div class="hero-gallery">
        <span class="gallery-glow" aria-hidden="true" />
        <el-carousel v-if="featured.length" class="poster-carousel" :interval="4000" arrow="hover" indicator-position="outside" loop height="340px">
          <el-carousel-item v-for="movie in featured" :key="movie.movie_id">
            <RouterLink class="carousel-slide" :to="`/movies/${movie.movie_id}`" :aria-label="`查看 ${movie.movielens_title} 详情`">
              <MoviePoster :path="movie.poster_path" :title="movie.movielens_title" :movie-id="movie.movie_id" :year="movie.release_year" :genres="movie.genres" />
              <span class="carousel-caption"><strong>{{ movie.movielens_title }}</strong><em>{{ movie.release_year }}</em></span>
            </RouterLink>
          </el-carousel-item>
        </el-carousel>
        <div v-else class="gallery-empty" aria-hidden="true"><span>华</span><p>正在整理片单</p></div>
        <div class="gallery-caption"><span>正在放映</span><strong>NOW SHOWING</strong></div>
      </div>
    </section>

    <div class="feature-strip">
      <p><span class="feature-icon"><el-icon aria-hidden="true"><Reading /></el-icon></span><span><strong>真实片库</strong><small>保留原始 MovieLens 电影标识</small></span></p>
      <p><span class="feature-icon"><el-icon aria-hidden="true"><Search /></el-icon></span><span><strong>自由探索</strong><small>按片名与类型发现电影</small></span></p>
      <p><span class="feature-icon"><el-icon aria-hidden="true"><Star /></el-icon></span><span><strong>智能推荐</strong><small>热门、内容、协同、矩阵分解与冷启动</small></span></p>
      <RouterLink to="/movies" class="feature-link">开始浏览 <span aria-hidden="true">↗</span></RouterLink>
    </div>

    <section class="recommendation-section">
      <div class="section-heading"><div><p class="eyebrow">MADE FOR YOUR TASTE</p><h2>你的下一部<span class="heading-dot">.</span></h2><p class="muted">{{ isNewUser ? '还是新观众？先看全场热门，或按兴趣类型开启冷启动推荐。' : '评分与收藏记录喜好，推荐结果随你的最新评分实时更新。' }}</p></div><RouterLink to="/experiments" class="text-link">查看实验室 →</RouterLink></div>
      <div class="recommendation-columns">
        <AlgorithmPanel :label="primaryPanel.label" :algorithm="primaryPanel.algorithm" :endpoint="primaryPanel.endpoint" />
        <AlgorithmPanel :label="secondaryPanel.label" :algorithm="secondaryPanel.algorithm" :endpoint="secondaryPanel.endpoint" />
      </div>
    </section>

    <section class="browse-section">
      <div class="section-heading"><div><p class="eyebrow">THE FILM ARCHIVE</p><h2>从片库出发<span class="heading-dot">.</span></h2><p class="muted">按原始电影编号展示，探索属于你的下一部。</p></div><RouterLink to="/movies" class="text-link">查看全部 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink></div>
      <StatePanel :loading="loading" :error="error" :empty="!!data && !data.items.length" @retry="fetchMovies"><div class="movie-grid"><MovieCard v-for="movie in data?.items" :key="movie.movie_id" :movie="movie" /></div></StatePanel>
    </section>
  </div>
</template>
<style scoped>
.hero-stage{position:relative;display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,320px);gap:60px;padding:52px 48px;border:1px solid var(--border);border-radius:18px;overflow:hidden;background:radial-gradient(90% 120% at 100% 0%,#f06a5017,transparent 55%),linear-gradient(120deg,#141b26,#10151e 65%,#151c27)}
.hero-kicker{display:inline-flex;align-items:center;gap:9px;font-size:10px;letter-spacing:.24em;color:var(--muted)}
.kicker-dot{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 5px #f06a5020}
.hero-copy{position:relative;z-index:1;display:flex;flex-direction:column;justify-content:center}
.hero-stage h1{font-family:var(--font-display);font-size:clamp(38px,4.4vw,62px);line-height:1.22;letter-spacing:-.01em;margin:20px 0 18px;font-weight:600}
.hero-stage h1 em{font-style:normal;color:var(--accent);position:relative}
.hero-description{color:var(--muted);line-height:1.95;font-size:15px}
.hero-actions{display:flex;gap:14px;margin-top:26px;flex-wrap:wrap}
.hero-stats{display:flex;gap:34px;margin:34px 0 0;padding-top:22px;border-top:1px solid var(--border);flex-wrap:wrap}
.hero-stats dt{font-size:10px;letter-spacing:.16em;color:var(--muted)}
.hero-stats dd{margin:6px 0 0;font-family:Georgia,serif;font-size:26px;color:var(--text);line-height:1}
.hero-stats dd small{font-size:12px;font-family:inherit;color:var(--muted);margin-left:2px}
.hero-gallery{position:relative;min-height:340px;display:flex;align-items:center;justify-content:center;padding-left:20px}
.gallery-glow{position:absolute;width:320px;height:320px;border-radius:50%;background:radial-gradient(circle,#f06a5033,transparent 68%);filter:blur(20px);pointer-events:none}
.poster-carousel{width:100%;max-width:280px;border-radius:14px;overflow:visible;flex-shrink:0}
.poster-carousel :deep(.el-carousel__item){display:flex;align-items:center;justify-content:center}
.poster-carousel :deep(.el-carousel__indicators--outside){bottom:-34px}
.poster-carousel :deep(.el-carousel__button){background:#f06a5080}
.poster-carousel :deep(.el-carousel__arrow){background:#00000055;color:#fff}
.carousel-slide{position:relative;display:block;width:100%;border-radius:12px;overflow:hidden;box-shadow:0 26px 50px #00000066;transition:transform .4s cubic-bezier(.2,.7,.3,1)}
.carousel-slide:hover{transform:translateY(-8px) scale(1.02)}
.carousel-slide .el-image,.carousel-slide img{display:block;width:100%}
.carousel-caption{position:absolute;left:0;right:0;bottom:0;padding:30px 14px 12px;background:linear-gradient(transparent,#000000cc);color:#fff;display:flex;flex-direction:column;gap:2px;font-family:var(--font-display)}
.carousel-caption strong{font-size:14px;font-weight:600;line-height:1.3}
.carousel-caption em{font-style:normal;font-size:11px;color:#f06a50;letter-spacing:.08em}
.gallery-empty{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:var(--muted);font-size:12px;letter-spacing:.2em}
.gallery-empty span{width:76px;height:76px;border-radius:18px;border:1px solid #f06a5055;display:grid;place-items:center;font-family:var(--font-display);font-size:32px;color:var(--accent)}
.gallery-caption{position:absolute;bottom:-6px;right:0;display:flex;flex-direction:column;align-items:flex-end;gap:2px;font-size:9px;letter-spacing:.24em;color:var(--muted)}
.gallery-caption strong{font-size:10px;color:var(--accent);letter-spacing:.2em}
.feature-strip{display:flex;align-items:center;gap:26px;justify-content:space-between;padding:24px 4px;border-bottom:1px solid var(--border);font-size:12px;flex-wrap:wrap}
.feature-strip p{display:flex;align-items:center;gap:12px}
.feature-icon{width:36px;height:36px;border-radius:10px;border:1px solid var(--border);display:grid;place-items:center;color:var(--accent);background:#f06a500d}
.feature-strip strong{display:block;font-size:12px;color:var(--text);font-weight:600}
.feature-strip small{display:block;color:var(--muted);font-size:11px;margin-top:2px}
.feature-link{color:var(--accent);white-space:nowrap;min-height:32px;display:inline-flex;align-items:center}
.browse-section,.recommendation-section{margin-top:46px}
.recommendation-columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}
@media(max-width:1100px){.hero-stage{padding:40px 32px;gap:32px;grid-template-columns:minmax(0,1fr) minmax(220px,260px)}.hero-gallery{min-height:300px;padding-left:0}.poster-carousel{max-width:220px}}
@media(max-width:860px){.hero-stage{grid-template-columns:1fr;padding:36px 28px;gap:32px}.hero-gallery{min-height:290px;order:-1;padding-left:0}.hero-stats{gap:26px}.recommendation-columns{grid-template-columns:1fr}}
@media(max-width:540px){.hero-stage{padding:26px 20px;border-radius:14px;gap:24px}.hero-gallery{min-height:230px}.poster-carousel{max-width:180px}.hero-stage h1{font-size:34px;margin:14px 0 12px}.hero-description{font-size:13px}.hero-stats{gap:18px;margin-top:24px;padding-top:16px}.hero-stats dd{font-size:22px}.feature-strip{gap:14px}.feature-strip .feature-icon{width:30px;height:30px}.feature-link{display:none}.hero-actions .button{padding:10px 14px}}
</style>
