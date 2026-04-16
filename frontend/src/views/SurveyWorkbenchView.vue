<script setup lang="ts">
import RunPanel from '../components/workbench/RunPanel.vue'
import CaseList from '../components/workbench/CaseList.vue'
import CaseBoard from '../components/workbench/CaseBoard.vue'
</script>

<template>
  <div class="workbench-page">
    <header class="workbench-page__header">
      <h1>Survey 判定工作台</h1>
      <p>支持按路径执行 kmer / nt / survey，左侧列表点击后右侧展示详情看板。</p>
    </header>

    <RunPanel />

    <section class="workbench-page__main">
      <div class="workbench-page__list">
        <CaseList />
      </div>
      <div class="workbench-page__board">
        <CaseBoard />
      </div>
    </section>
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
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(460px, 1fr) minmax(560px, 1.2fr);
  min-height: calc(100vh - 240px);
}

.workbench-page__list,
.workbench-page__board {
  min-height: 100%;
}

@media (max-width: 1400px) {
  .workbench-page__main {
    grid-template-columns: 1fr;
  }
}
</style>
