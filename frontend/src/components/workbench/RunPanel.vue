<script setup lang="ts">
import { computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useCasesStore } from '../../stores/cases'

const store = useCasesStore()

const form = reactive({
  sampleDir: '',
  sampleCode: '',
})

const canRun = computed(() => form.sampleDir.trim().length > 0)

async function onCheckFiles() {
  if (!canRun.value) {
    ElMessage.warning('请输入 sample_dir')
    return
  }
  await store.checkFiles(form.sampleDir.trim())
}

async function onRun(type: 'kmer' | 'nt' | 'survey') {
  if (!canRun.value) {
    ElMessage.warning('请输入 sample_dir')
    return
  }
  await store.runByPath(type, form.sampleDir.trim(), form.sampleCode.trim() || undefined)
}
</script>

<template>
  <el-card shadow="never" class="run-panel">
    <template #header>
      <div class="run-panel__header">路径执行区</div>
    </template>

    <el-form label-position="top" class="run-panel__form">
      <el-form-item label="sample_dir">
        <el-input
          v-model="form.sampleDir"
          placeholder="请输入样本目录路径，例如 data/shenshaoqi_data_v2/1"
          clearable
        />
      </el-form-item>

      <el-form-item label="sample_code（可选）">
        <el-input v-model="form.sampleCode" placeholder="可选，留空由后端推断" clearable />
      </el-form-item>
    </el-form>

    <div class="run-panel__actions">
      <el-button :loading="store.checkingFiles" @click="onCheckFiles">仅检查文件</el-button>
      <el-button :loading="store.runningType === 'kmer'" @click="onRun('kmer')">执行 kmer</el-button>
      <el-button :loading="store.runningType === 'nt'" @click="onRun('nt')">执行 nt</el-button>
      <el-button type="primary" :loading="store.runningType === 'survey'" @click="onRun('survey')">
        执行 survey
      </el-button>
    </div>

    <el-alert
      v-if="store.fileCheckResult"
      class="run-panel__file-check"
      type="info"
      :closable="false"
      show-icon
      :title="store.fileCheckResult.message"
    >
      <div>kmer_complete: {{ store.fileCheckResult.file_check.kmer_complete }}</div>
      <div>nt_complete: {{ store.fileCheckResult.file_check.nt_complete }}</div>
      <div>complete: {{ store.fileCheckResult.file_check.complete }}</div>
      <div v-if="store.fileCheckResult.file_check.missing.length > 0">
        missing: {{ store.fileCheckResult.file_check.missing.join(', ') }}
      </div>
    </el-alert>
  </el-card>
</template>

<style scoped>
.run-panel__header {
  font-size: 16px;
  font-weight: 600;
}

.run-panel__form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.run-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.run-panel__file-check {
  margin-top: 12px;
}

@media (max-width: 900px) {
  .run-panel__form {
    grid-template-columns: 1fr;
  }
}
</style>
