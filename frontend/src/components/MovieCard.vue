<script setup lang="ts">
import type { Movie } from '../types'
import MoviePoster from './MoviePoster.vue'
import { genreLabels } from '../genres'
defineProps<{ movie: Movie }>()
</script>
<template>
  <article class="film-card">
    <RouterLink class="film-link" :to="`/movies/${movie.movie_id}`" :aria-label="`查看 ${movie.title_zh || movie.movielens_title} 详情`">
      <div class="film-poster">
        <MoviePoster :path="movie.poster_path" :title="movie.movielens_title"
          :movie-id="movie.movie_id" :year="movie.release_year" :genres="movie.genres" />
        <div class="film-veil" aria-hidden="true"><span>查看详情</span><i>→</i></div>
        <span class="film-id">#{{ movie.movie_id }}</span>
        <span v-if="movie.rating" class="film-rating">★ {{ movie.rating }}</span>
      </div>
      <div class="film-info">
        <h3>{{ movie.title_zh || movie.movielens_title }}</h3>
        <p class="film-sub"><span class="film-year">{{ movie.release_year || '年份未收录' }}</span><span>{{ genreLabels(movie.genres, 2).join(' / ') || '类型未收录' }}</span></p>
      </div>
    </RouterLink>
  </article>
</template>
<style scoped>
.film-card{min-width:0}
.film-link{display:block;border-radius:12px}
.film-poster{position:relative;border-radius:12px;overflow:hidden;box-shadow:0 16px 30px #00000038;transition:transform .28s cubic-bezier(.2,.7,.3,1),box-shadow .28s}
.film-poster :deep(img){transition:transform .55s cubic-bezier(.2,.7,.3,1)}
.film-link:hover .film-poster{transform:translateY(-5px);box-shadow:0 22px 42px #00000055}
.film-link:hover .film-poster :deep(img){transform:scale(1.05)}
.film-veil{position:absolute;inset:0;display:flex;align-items:flex-end;justify-content:space-between;gap:12px;padding:16px;background:linear-gradient(180deg,#0000 42%,#090d13e0);color:#f5efe6;font-size:12px;letter-spacing:.08em;opacity:0;transition:opacity .25s}
.film-veil i{font-style:normal;width:28px;height:28px;border-radius:50%;background:var(--accent);color:var(--ink);display:grid;place-items:center;font-size:14px}
.film-link:hover .film-veil,.film-link:focus-visible .film-veil{opacity:1}
.film-id{position:absolute;top:10px;left:10px;background:#0a0f16b8;backdrop-filter:blur(6px);border:1px solid #ffffff1f;border-radius:999px;font-size:9px;padding:2px 8px;color:#cdd6e2;font-family:monospace}
.film-rating{position:absolute;bottom:10px;right:10px;background:#f06a50f2;color:#1b100c;border-radius:999px;padding:2px 9px;font-size:11px;font-weight:600;box-shadow:0 6px 14px #00000040}
.film-info{margin-top:13px;padding:0 2px}
.film-info h3{font-size:15px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;transition:color .18s}
.film-sub{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.film-year{color:var(--accent);font-family:Georgia,serif;letter-spacing:.03em}
.film-sub span+span{overflow:hidden;text-overflow:ellipsis}
.film-link:hover h3{color:var(--accent)}
@media(max-width:540px){.film-info h3{font-size:13px}.film-sub{font-size:11px}.film-veil{padding:12px;font-size:11px}}
</style>
