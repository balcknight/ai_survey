<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useCasesStore } from '../../stores/cases'
import type { CaseSummary } from '../../types/case'

const store = useCasesStore()

const statusOptions = [
  { label: '全部', value: '' },
  { label: 'created', value: 'created' },
  { label: 'kmer_done', value: 'kmer_done' },
  { label: 'nt_done', value: 'nt_done' },
  { label: 'judged', value: 'judged' },
  { label: 'failed', value: 'failed' },
]

const finalLevelOptions = [
  { label: '全部', value: '' },
  { label: '正常', value: '正常' },
  { label: '轻度污染', value: '轻度污染' },
  { label: '重度污染', value: '重度污染' },
  { label: 'fail', value: 'fail' },
]

const shouldTransferOptions = [
  { label: '全部', value: '' },
  { label: '是', value: '是' },
  { label: '否', value: '否' },
]

const currentPage = computed({
  get: () => Math.floor(store.filters.offset / store.filters.limit) + 1,
  set: (page: number) => {
    store.filters.offset = (page - 1) * store.filters.limit
  },
})

async function loadList() {
  await store.fetchList()
  if (store.list.length > 0 && store.selectedCaseId === null) {
    await store.selectCase(store.list[0].id)
  }
}

function onRowClick(row: CaseSummary) {
  store.selectCase(row.id)
}

async function onSearch() {
  store.filters.offset = 0
  await loadList()
}

async function onReset() {
  store.resetFilters()
  await loadList()
}

async function onPageChange(page: number) {
  currentPage.value = page
  await loadList()
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
      <el-input v-model="store.filters.target_species" placeholder="target_species" clearable />
      <el-select v-model="store.filters.final_level" placeholder="final_level">
        <el-option v-for="item in finalLevelOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="store.filters.should_transfer" placeholder="should_transfer">
        <el-option v-for="item in shouldTransferOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="store.filters.status" placeholder="status">
        <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
    </div>

    <div class="filters filters-actions">
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <el-table
      v-loading="store.loadingList"
      :data="store.list"
      height="calc(100vh - 450px)"
      highlight-current-row
      row-key="id"
      @row-click="onRowClick"
    >
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="sample_code" label="sample_code" min-width="160" show-overflow-tooltip />
      <el-table-column prop="target_species" label="target_species" min-width="120" show-overflow-tooltip />
      <el-table-column prop="final_level" label="final_level" width="110" />
      <el-table-column prop="should_transfer" label="transfer" width="90" />
      <el-table-column prop="status" label="status" width="110" />
      <el-table-column prop="updated_at" label="updated_at" min-width="170" show-overflow-tooltip />
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
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.filters-actions {
  grid-template-columns: 100px 100px;
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
