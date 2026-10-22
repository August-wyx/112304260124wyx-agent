// MovieLens genres are stored in English; the interface presents them in Chinese
// while every request still sends the original value.
const GENRE_LABELS: Record<string, string> = {
  Action: '动作', Adventure: '冒险', Animation: '动画', Children: '儿童', Comedy: '喜剧',
  Crime: '犯罪', Documentary: '纪录', Drama: '剧情', Fantasy: '奇幻', 'Film-Noir': '黑色电影',
  Horror: '恐怖', Musical: '音乐', Mystery: '悬疑', Romance: '爱情', 'Sci-Fi': '科幻',
  Thriller: '惊悚', War: '战争', Western: '西部', IMAX: 'IMAX',
}

export function genreLabel(value: string): string {
  return GENRE_LABELS[value] || value
}

export function genreLabels(values: string[] | null | undefined, limit?: number): string[] {
  const labels = (values || []).map(genreLabel)
  return limit ? labels.slice(0, limit) : labels
}

export function genreText(values: string[] | null | undefined, separator = ' / '): string {
  return genreLabels(values).join(separator)
}
