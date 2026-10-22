<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Right } from '@element-plus/icons-vue'
import { useAuth } from './stores/auth'
import { ElMessage } from 'element-plus'
import { errorMessage, ApiError, ensureCsrf } from './api'
import { ref } from 'vue'
const auth = useAuth(), route = useRoute(), router = useRouter()
const signingOut = ref(false)
const csrfError = ref(false)
async function logout() {
  signingOut.value = true
  try { await auth.signOut(); ElMessage.success('已退出，原会话已失效'); await router.push('/') }
  catch (e) {
    csrfError.value = e instanceof ApiError && e.code === 'CSRF_REJECTED'
    ElMessage.error(errorMessage(e))
  } finally { signingOut.value = false }
}
async function recover() {
  try { await ensureCsrf(true); csrfError.value = false; ElMessage.success('安全凭据已更新，请重新操作') }
  catch (e) { ElMessage.error(errorMessage(e)) }
}
function expired() {
  const hadAccount = !!auth.account
  auth.expire()
  if (hadAccount && route.meta.requiresAuth) void router.replace({ path: '/login', query: { redirect: route.fullPath, reason: 'expired' } })
}
window.addEventListener('session-expired', expired)
onBeforeUnmount(() => window.removeEventListener('session-expired', expired))
</script>
<template>
  <a class="skip-link" href="#main">跳到主要内容</a>
  <header class="site-header"><div class="header-inner">
    <RouterLink class="brand" to="/" aria-label="华文影视首页"><span class="brand-mark" aria-hidden="true">华</span><span class="brand-copy"><strong>华文影视</strong><small>HUWEN CINEMA</small></span></RouterLink>
    <nav class="main-nav" aria-label="主导航"><RouterLink to="/" exact-active-class="active"><i>01</i>发现</RouterLink><RouterLink to="/movies" active-class="active"><i>02</i>电影库</RouterLink><RouterLink to="/experiments" active-class="active"><i>03</i>推荐实验室<span class="nav-dot" /></RouterLink></nav>
    <div class="account-nav"><template v-if="auth.account"><RouterLink to="/profile" class="account-link"><el-icon aria-hidden="true"><User /></el-icon><span>{{ auth.account.login_name }}</span></RouterLink><el-button text :loading="signingOut" @click="logout">退出</el-button></template><RouterLink v-else to="/login" class="login-link">登录 / 注册 <el-icon aria-hidden="true"><Right /></el-icon></RouterLink></div>
  </div></header>
  <main id="main" tabindex="-1"><div v-if="auth.restoreError" class="global-notice" role="alert">{{ errorMessage(auth.restoreError) }} <el-button text @click="router.go(0)">重新连接</el-button></div><div v-if="csrfError" class="global-notice"><el-button @click="recover">更新安全凭据</el-button></div><RouterView /></main>
  <footer class="site-footer">
    <div class="footer-grid">
      <div class="footer-brand-block"><span class="footer-mark" aria-hidden="true">华</span><div><strong>华文影视</strong><p>每一份喜好，都是发现的开始。</p></div></div>
      <nav class="footer-links" aria-label="页脚导航"><RouterLink to="/">发现</RouterLink><RouterLink to="/movies">电影库</RouterLink><RouterLink to="/experiments">推荐实验室</RouterLink><RouterLink to="/profile">我的片单</RouterLink></nav>
      <div class="footer-meta"><span>MovieLens 真实电影数据</span><span>推荐算法及应用 · 课程实验</span><span>HUWEN CINEMA © 2026</span></div>
    </div>
  </footer>
</template>
<style scoped>
.site-header{position:sticky;top:0;z-index:30;background:#0c0f15d9;backdrop-filter:blur(20px);border-bottom:1px solid var(--border)}
.header-inner{max-width:1360px;margin:auto;padding:0 48px;height:78px;display:flex;align-items:center;gap:38px}
.brand{display:flex;align-items:center;gap:13px;flex-shrink:0}
.brand-mark{width:40px;height:40px;border-radius:12px;background:linear-gradient(145deg,var(--accent),#c14e38);color:#fff;display:grid;place-items:center;font-family:var(--font-display);font-size:20px;box-shadow:0 10px 24px #f06a5033}
.brand-copy strong{display:block;font-family:var(--font-display);font-size:22px;letter-spacing:.06em;line-height:1.1}
.brand-copy small{display:block;font-size:9px;letter-spacing:.28em;color:var(--muted);margin-top:3px}
.main-nav{display:flex;gap:6px;align-self:stretch;margin-right:auto}
.main-nav a{display:flex;align-items:center;gap:9px;color:var(--muted);padding:0 15px;border-radius:10px;min-height:42px;align-self:center;font-size:14px;transition:color .18s,background .18s}
.main-nav a i{font-style:normal;font-family:Georgia,serif;font-size:10px;color:#6f7b8b;letter-spacing:.06em}
.main-nav a:hover,.main-nav a.active{color:var(--text);background:#ffffff08}
.main-nav a.active i{color:var(--accent)}
.nav-dot{width:5px;height:5px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 4px #f06a5022}
.account-nav{display:flex;align-items:center;gap:12px}
.account-link,.login-link{display:flex;align-items:center;gap:9px;min-height:40px;padding:0 14px;border:1px solid var(--border);border-radius:999px;font-size:13px;transition:border-color .18s,color .18s}
.account-link:hover,.login-link:hover{border-color:var(--accent);color:var(--accent)}
.account-link span{max-width:125px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.login-link .el-icon{color:var(--accent)}
.site-footer{max-width:1360px;margin:72px auto 0;border-top:1px solid var(--border);padding:34px 48px 40px}
.footer-grid{display:flex;justify-content:space-between;gap:32px;flex-wrap:wrap;align-items:center}
.footer-brand-block{display:flex;align-items:center;gap:14px}
.footer-mark{width:34px;height:34px;border-radius:10px;border:1px solid #f06a5055;color:var(--accent);display:grid;place-items:center;font-family:var(--font-display);font-size:16px}
.footer-brand-block strong{font-family:var(--font-display);font-size:17px;letter-spacing:.08em}
.footer-brand-block p{color:var(--muted);font-size:12px;margin-top:3px}
.footer-links{display:flex;gap:26px;font-size:13px;flex-wrap:wrap}
.footer-links a{color:var(--muted)}
.footer-links a:hover{color:var(--accent)}
.footer-meta{font-size:11px;display:flex;flex-direction:column;align-items:flex-end;gap:4px;color:var(--muted);text-align:right}
@media(max-width:1100px){.header-inner{padding-inline:32px;gap:24px}.site-footer{padding-inline:32px}}
@media(max-width:860px){.header-inner{height:auto;min-height:74px;padding:14px 24px;flex-wrap:wrap;gap:12px}.main-nav{order:3;width:100%;justify-content:space-between;gap:4px}.main-nav a{flex:1;justify-content:center;min-height:40px;font-size:13px}.main-nav a i{display:none}.account-nav{margin-left:auto}.footer-grid{flex-direction:column;align-items:flex-start}.footer-meta{align-items:flex-start;text-align:left}.site-footer{padding:26px 24px 32px;margin-top:48px}}
@media(max-width:540px){.header-inner{padding:12px 18px}.brand-copy strong{font-size:20px}.brand-copy small{font-size:8px}.account-link span{max-width:80px}.footer-links{gap:16px;font-size:12px}}
</style>
