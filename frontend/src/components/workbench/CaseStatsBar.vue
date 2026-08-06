<script setup lang="ts">
import { computed } from 'vue'
import { useCasesStore } from '../../stores/cases'

const store = useCasesStore()

function levelCount(level: string): number {
  return store.stats?.by_final_level?.[level] ?? 0
}

const reviewedText = computed(() => {
  if (!store.stats) return '-'
  return `${store.stats.reviewed} / ${store.stats.total}`
})

function valueText(value: number): string {
  return store.stats ? String(value) : '-'
}
</script>

<template>
  <div class="stats-bar" v-loading="store.loadingStats">
    <div class="stat-card">
      <div class="stat-card__value">{{ valueText(store.stats?.total ?? 0) }}</div>
      <div class="stat-card__label">样本总数</div>
    </div>
    <div class="stat-card stat-card--success">
      <div class="stat-card__value">{{ valueText(levelCount('正常')) }}</div>
      <div class="stat-card__label">正常</div>
    </div>
    <div class="stat-card stat-card--danger">
      <div class="stat-card__value">{{ valueText(levelCount('重度污染')) }}</div>
      <div class="stat-card__label">重度污染</div>
    </div>
    <div class="stat-card stat-card--warning">
      <div class="stat-card__value">{{ valueText(levelCount('待人工复核')) }}</div>
      <div class="stat-card__label">待人工复核</div>
    </div>
    <div class="stat-card stat-card--primary">
      <div class="stat-card__value">{{ reviewedText }}</div>
      <div class="stat-card__label">已审核 / 总数</div>
    </div>
  </div>
</template>

<style scoped>
.stats-bar {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 12px;
}

.stat-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-card__value {
  font-size: 24px;
  font-weight: 700;
  color: #0b2545;
  line-height: 1.2;
}

.stat-card__label {
  font-size: 13px;
  color: #5b6b79;
}

.stat-card--success .stat-card__value {
  color: #18a058;
}

.stat-card--danger .stat-card__value {
  color: #d03050;
}

.stat-card--warning .stat-card__value {
  color: #f0a020;
}

.stat-card--primary .stat-card__value {
  color: #2080f0;
}

@media (max-width: 900px) {
  .stats-bar {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
</style>
