import { createRouter, createWebHistory } from 'vue-router'
import SurveyWorkbenchView from '../views/SurveyWorkbenchView.vue'
import ManualReviewPrototypeView from '../views/ManualReviewPrototypeView.vue'

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
    {
      path: '/review-prototype',
      name: 'review-prototype',
      component: ManualReviewPrototypeView,
    },
  ],
})

export default router
