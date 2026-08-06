<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function safeRedirect(raw: unknown): string {
  // 防开放重定向：仅接受单 / 开头的站内路径，拒绝 // 开头。
  if (typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//')) {
    return raw
  }
  return '/cases'
}

async function onSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    await authStore.login(form.username, form.password)
    const target = safeRedirect(route.query.redirect)
    router.replace(target)
  } catch {
    // 401 的具体提示（用户名或密码错误）已由 http 拦截器统一弹出，这里仅恢复按钮态。
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card shadow="never" class="login-card">
      <h1 class="login-title">Survey 判定系统</h1>
      <p class="login-subtitle">请登录后继续</p>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="onSubmit">
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            autocomplete="username"
            clearable
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            autocomplete="current-password"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="login-button"
            :loading="submitting"
            @click="onSubmit"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  display: grid;
  place-items: center;
  min-height: 100vh;
  background: #f4f6f8;
  padding: 16px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  padding: 12px 8px 0;
}

.login-title {
  margin: 0;
  font-size: 22px;
  color: #0b2545;
  text-align: center;
}

.login-subtitle {
  margin: 8px 0 24px;
  color: #5b6b79;
  text-align: center;
}

.login-button {
  width: 100%;
}
</style>
