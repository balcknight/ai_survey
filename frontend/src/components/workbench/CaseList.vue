<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useCasesStore } from '../../stores/cases'
import type { CaseSummary } from '../../types/case'
import { getFinalLevelTagType } from '../../constants/case-tags'

const store = useCasesStore()

const reviewDecisionOptions = [
  { label: '全部', value: '' },
  { label: '流转', value: 'transfer' },
  { label: '不流转', value: 'no_transfer' },
]

const finalLevelOptions = [
  { label: '全部', value: '' },
  { label: '正常', value: '正常' },
  { label: '重度污染', value: '重度污染' },
  { label: '待人工复核', value: '待人工复核' },
]

const reviewStatusOptions = [
  { label: '全部', value: '' },
  { label: '未审核', value: 'unreviewed' },
  { label: '已审核', value: 'reviewed' },
]

function decisionText(value: string | null | undefined): string {
  if (!value) return '-'
  if (value === 'transfer' || value === 'rerun' || value === 'manual_transfer') return '流转'
  if (value === 'no_transfer' || value === 'confirm') return '不流转'
  return value
}

function formatDatetime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const currentPage = computed({
  get: () => Math.floor(store.filters.offset / store.filters.limit) + 1,
  set: (page: number) => {
    store.filters.offset = (page - 1) * store.filters.limit
  },
})

async function loadList() {
  await store.fetchList()
}

function onRowClick(row: CaseSummary) {
  store.selectCase(row.id)
}

async function onSearch() {
  store.filters.offset = 0
  await loadList()
}

async function onPageChange(page: number) {
  currentPage.value = page
  await loadList()
}

function rowClassName({ row }: { row: CaseSummary }) {
  return row.id === store.selectedCaseId ? 'case-list__row--active' : ''
}

onMounted(async () => {
  await loadList()
})
</script>

<template>
  <el-card shadow="never" class="case-list-card">
    <template #header>
      <div class="case-list-card__header">已判定样本列表</div>
    </template>

    <div class="filters">
      <el-input v-model="store.filters.stage_code" placeholder="stage_code（模糊）" clearable @change="onSearch" />
      <el-input v-model="store.filters.target_species" placeholder="物种（模糊）" clearable @change="onSearch" />
      <el-select v-model="store.filters.final_level" placeholder="final_level" @change="onSearch">
        <el-option v-for="item in finalLevelOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="store.filters.review_status" placeholder="审核状态" @change="onSearch">
        <el-option v-for="item in reviewStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="store.filters.review_final_decision" placeholder="审核结论" @change="onSearch">
        <el-option v-for="item in reviewDecisionOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
    </div>

    <el-table
      v-loading="store.loadingList"
      :data="store.list"
      height="calc(100vh - 400px)"
      highlight-current-row
      row-key="id"
      :current-row-key="store.selectedCaseId ?? undefined"
      :row-class-name="rowClassName"
      @row-click="onRowClick"
    >
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="stage_code" label="stage_code" min-width="140" show-overflow-tooltip />
      <el-table-column prop="target_species" label="target_species" min-width="120" show-overflow-tooltip />
      <el-table-column prop="final_level" label="final_level" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="getFinalLevelTagType(row.final_level)">
            {{ row.final_level || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最终决策" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.reviewed" size="small" :type="row.review_final_decision === 'no_transfer' || row.review_final_decision === 'confirm' ? 'danger' : 'success'">
            {{ decisionText(row.review_final_decision) }}
          </el-tag>
          <span v-else style="color: #909399; font-size: 12px;">未审核</span>
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" min-width="150">
        <template #default="{ row }">
          {{ formatDatetime(row.updated_at) }}
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pagination"
      background
      layout="prev, pager, next, total"
      :page-size="store.filters.limit"
      :total="store.total"
      :current-page="currentPage"
      @current-change="onPageChange"
    />
  </el-card>
</template>

<style scoped>
.case-list-card__header {
  font-size: 16px;
  font-weight: 600;
}

.filters {
  display: grid;
  grid-template-columns: repeat(5, minmax(110px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.pagination {
  margin-top: 12px;
  justify-content: flex-end;
}

@media (max-width: 1200px) {
  .filters {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
</style>

<style>
.case-list__row--active td.el-table__cell {
  background-color: #ecf5ff !important;
}
</style>
