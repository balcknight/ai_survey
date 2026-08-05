import axios from 'axios'
import { ElMessage } from 'element-plus'

const isDev = import.meta.env.DEV
const enableHttpLog = isDev && import.meta.env.VITE_ENABLE_HTTP_LOG !== 'false'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://10.11.0.6:8001',
  timeout: 60000,
})

http.interceptors.request.use((config) => {
  if (enableHttpLog) {
    console.info('[HTTP][Request]', {
      method: config.method?.toUpperCase(),
      url: `${config.baseURL ?? ''}${config.url ?? ''}`,
      params: config.params,
      data: config.data,
    })
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    if (enableHttpLog) {
      console.info('[HTTP][Response]', {
        method: response.config.method?.toUpperCase(),
        url: `${response.config.baseURL ?? ''}${response.config.url ?? ''}`,
        status: response.status,
        data: response.data,
      })
    }
    return response
  },
  (error) => {
    const status = error?.response?.status
    const detail = error?.response?.data?.detail

    if (!error?.response) {
      if (error?.code === 'ECONNABORTED') {
        ElMessage.error('请求超时，请检查网络或稍后重试')
      } else {
        ElMessage.error('网络连接失败，请确认后端服务可访问')
      }
    } else if (status === 409) {
      ElMessage.error(detail ?? '路径已存在记录，可使用重跑覆盖')
    } else if (status === 404) {
      ElMessage.error(detail ?? '目标记录不存在')
    } else if (status === 500) {
      ElMessage.error(detail ?? '服务器内部错误，请稍后重试')
    } else if (typeof status === 'number' && status >= 400) {
      ElMessage.error(detail ?? `请求失败（HTTP ${status}）`)
    } else {
      ElMessage.error(detail ?? error?.message ?? '请求失败')
    }

    if (enableHttpLog) {
      console.error('[HTTP][Error]', {
        method: error?.config?.method?.toUpperCase(),
        url: `${error?.config?.baseURL ?? ''}${error?.config?.url ?? ''}`,
        status,
        detail,
        message: error?.message,
      })
    }

    return Promise.reject(error)
  },
)

export default http
