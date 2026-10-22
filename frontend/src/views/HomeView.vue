<script setup lang="ts">
import { computed, onMounted } from 'vue'
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
const fetchMovies = () => load(async () => (await http.get<Page<Movie>>('/movies', { params: { per_page: 4 } })).data)
const featured = computed(() => (data.value?.items || []).slice(0, 3))
onMounted(fetchMovies)
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
        <div v-for="(movie, index) in featured" :key="movie.movie_id" class="gallery-item" :class="`gallery-item-${index + 1}`">
          <RouterLink :to="`/movies/${movie.movie_id}`" :aria-label="`查看 ${movie.movielens_title} 详情`">
            <MoviePoster :path="movie.poster_path" :title="movie.movielens_title" :movie-id="movie.movie_id" :year="movie.release_year" :genres="movie.genres" />
          </RouterLink>
        </div>
        <div v-if="!featured.length" class="gallery-empty" aria-hidden="true"><span>华</span><p>正在整理片单</p></div>
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
      <div class="section-heading"><div><p class="eyebrow">MADE FOR YOUR TASTE</p><h2>你的下一部<span class="heading-dot">.</span></h2><p class="muted">评分与收藏记录喜好，五种算法各自给出答案。</p></div><RouterLink to="/experiments" class="text-link">查看实验室 →</RouterLink></div>
      <div class="recommendation-columns"><AlgorithmPanel label="为你推荐" :endpoint="auth.account ? '/me/recommendations/content' : null" /><AlgorithmPanel label="热门推荐" :endpoint="auth.account ? '/me/recommendations/popular' : null" /></div>
    </section>

    <section class="browse-section">
      <div class="section-heading"><div><p class="eyebrow">THE FILM ARCHIVE</p><h2>从片库出发<span class="heading-dot">.</span></h2><p class="muted">按原始电影编号展示，探索属于你的下一部。</p></div><RouterLink to="/movies" class="text-link">查看全部 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink></div>
      <StatePanel :loading="loading" :error="error" :empty="!!data && !data.items.length" @retry="fetchMovies"><div class="movie-grid"><MovieCard v-for="movie in data?.items" :key="movie.movie_id" :movie="movie" /></div></StatePanel>
    </section>
  </div>
</template>
<style scoped>
.hero-stage{position:relative;display:grid;grid-template-columns:1.05fr .95fr;gap:40px;padding:52px 48px;border:1px solid var(--border);border-radius:18px;overflow:hidden;background:radial-gradient(90% 120% at 100% 0%,#f06a5017,transparent 55%),linear-gradient(120deg,#141b26,#10151e 65%,#151c27)}
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
.hero-gallery{position:relative;min-height:340px;display:flex;align-items:center;justify-content:center}
.gallery-glow{position:absolute;width:320px;height:320px;border-radius:50%;background:radial-gradient(circle,#f06a5033,transparent 68%);filter:blur(20px)}
.gallery-item{position:absolute;width:168px;transition:transform .45s cubic-bezier(.2,.7,.3,1);border-radius:12px;box-shadow:0 26px 50px #00000066}
.gallery-item-1{transform:translate(-108px,4px) rotate(-9deg);z-index:1;width:150px;opacity:.82}
.gallery-item-2{transform:translate(0,-18px);z-index:3;width:186px}
.gallery-item-3{transform:translate(106px,14px) rotate(9deg);z-index:2;width:150px;opacity:.82}
.gallery-item:hover{transform:translateY(-12px) rotate(0);z-index:4;opacity:1}
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
@media(max-width:1100px){.hero-stage{padding:40px 32px;gap:24px}.hero-gallery{min-height:300px}.gallery-item-1,.gallery-item-3{width:128px}.gallery-item-2{width:158px}}
@media(max-width:860px){.hero-stage{grid-template-columns:1fr;padding:36px 28px}.hero-gallery{min-height:290px;order:-1}.hero-stats{gap:26px}.recommendation-columns{grid-template-columns:1fr}}
@media(max-width:540px){.hero-stage{padding:26px 20px;border-radius:14px}.hero-gallery{min-height:230px}.gallery-item-1{transform:translate(-78px,2px) rotate(-9deg);width:100px}.gallery-item-2{width:132px}.gallery-item-3{transform:translate(78px,10px) rotate(9deg);width:100px}.hero-stage h1{font-size:34px;margin:14px 0 12px}.hero-description{font-size:13px}.hero-stats{gap:18px;margin-top:24px;padding-top:16px}.hero-stats dd{font-size:22px}.feature-strip{gap:14px}.feature-strip .feature-icon{width:30px;height:30px}.feature-link{display:none}.hero-actions .button{padding:10px 14px}}
</style>
