import { createRouter, createWebHistory } from 'vue-router'
import SurveyWorkbenchView from '../views/SurveyWorkbenchView.vue'
import ManualReviewPrototypeView from '../views/ManualReviewPrototypeView.vue'
import LoginView from '../views/LoginView.vue'
import { getToken } from '../utils/auth-token'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/cases',
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { public: true },
    },
    {
      path: '/cases',
      name: 'cases',
      component: SurveyWorkbenchView,
    },
    {
      path: '/review-prototype',
      name: 'review-prototype',
      component: ManualReviewPrototypeView,
    },
  ],
})

// 全局登录守卫：除 meta.public 外均需登录。
router.beforeEach(async (to) => {
  if (to.meta.public) return true

  const token = getToken()
  if (!token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 已有 token 但内存中无用户信息（如刷新页面）时，拉取一次 /me 校验。
  const auth = useAuthStore()
  if (!auth.currentUser) {
    try {
      await auth.fetchMe()
    } catch {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }
  return true
})

export default router
