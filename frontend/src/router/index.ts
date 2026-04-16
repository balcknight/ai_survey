import { createRouter, createWebHistory } from 'vue-router'
import SurveyWorkbenchView from '../views/SurveyWorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/cases',
    },
    {
      path: '/cases',
      name: 'cases',
      component: SurveyWorkbenchView,
    },
  ],
})

export default router
