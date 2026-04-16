# Survey Frontend (V1)

## 开发环境
- Node.js >= 20

## 启动
```bash
cd frontend
npm install
npm run dev
```

## 构建
```bash
npm run build
npm run preview
```

## 环境变量
默认后端地址：`http://192.168.20.24:8001`

如需覆盖，可创建 `.env.local`：
```bash
VITE_API_BASE_URL=http://192.168.20.24:8001
VITE_ENABLE_HTTP_LOG=true
```

- `VITE_ENABLE_HTTP_LOG` 仅在开发环境生效，默认开启；设置为 `false` 可关闭请求日志。

## 联调清单
- 参考文档：`docs/frontend_joint_debug_checklist.md`
