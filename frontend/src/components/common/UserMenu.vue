<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

function onLogout() {
  // 退出登录非高风险操作，不做二次确认。
  authStore.logout()
}
</script>

<template>
  <div class="user-menu" v-if="authStore.currentUser">
    <span class="user-menu__name">{{ authStore.currentUser.display_name || authStore.currentUser.username }}</span>
    <el-button link type="primary" @click="onLogout">退出登录</el-button>
  </div>
</template>

<style scoped>
.user-menu {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.user-menu__name {
  color: #0b2545;
  font-weight: 600;
}
</style>
