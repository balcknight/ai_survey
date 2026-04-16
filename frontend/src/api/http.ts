import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://192.168.20.24:8001',
  timeout: 60000,
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const detail = error?.response?.data?.detail

    if (status === 409) {
      ElMessage.error(detail ?? '路径已存在记录，可使用重跑覆盖')
    } else if (status === 404) {
      ElMessage.error(detail ?? '目标记录不存在')
    } else if (status === 500) {
      ElMessage.error(detail ?? '服务器内部错误，请稍后重试')
    } else {
      ElMessage.error(detail ?? error?.message ?? '请求失败')
    }

    return Promise.reject(error)
  },
)

export default http
