<script setup lang="ts">
import { useRouter } from 'vue-router'
import CaseStatsBar from '../components/workbench/CaseStatsBar.vue'
import CaseList from '../components/workbench/CaseList.vue'
import CaseBoard from '../components/workbench/CaseBoard.vue'
import UserMenu from '../components/common/UserMenu.vue'
import { useCasesStore } from '../stores/cases'

const store = useCasesStore()
const router = useRouter()
</script>

<template>
  <div class="workbench-page">
    <header class="workbench-page__header">
      <div class="workbench-page__header-top">
        <h1>Survey 判定工作台</h1>
        <div class="workbench-page__header-actions">
          <UserMenu />
          <el-button type="primary" plain @click="router.push('/review-prototype')">进入人工审核</el-button>
        </div>
      </div>
      <p>点击样本以抽屉形式展示判定详情看板，支持按分期号与物种模糊检索。</p>
    </header>

    <CaseStatsBar />

    <section class="workbench-page__main">
      <div class="workbench-page__list">
        <CaseList />
      </div>
    </section>

    <el-drawer
      v-model="store.boardDrawerVisible"
      direction="rtl"
      size="56%"
      destroy-on-close
      :with-header="false"
      class="workbench-page__drawer"
      @closed="store.closeBoardDrawer"
    >
      <CaseBoard />
    </el-drawer>
  </div>
</template>

<style scoped>
.workbench-page {
  display: grid;
  gap: 12px;
  min-height: 100vh;
  padding: 16px;
  background: #f4f6f8;
}

.workbench-page__header {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
  padding: 12px 16px;
}

.workbench-page__header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.workbench-page__header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.workbench-page__header h1 {
  margin: 0;
  font-size: 22px;
  color: #0b2545;
}

.workbench-page__header p {
  margin: 8px 0 0;
  color: #5b6b79;
}

.workbench-page__main {
  min-height: calc(100vh - 240px);
}

.workbench-page__list {
  min-height: 100%;
}

.workbench-page__drawer :deep(.el-drawer__body) {
  padding: 0;
}

@media (max-width: 1200px) {
  .workbench-page__drawer {
    width: 92% !important;
  }
}
</style>
