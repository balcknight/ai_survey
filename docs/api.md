# 外部调用接口（压缩包上传）

## 接口
- `POST /api/cases/run-by-archive`
- `Content-Type: multipart/form-data`

## 请求参数
1. `archive`：样本文件压缩包（仅支持 `.zip`）
2. `stage_code`：分期编号
3. `sample_name`：样本名称（核酸编号，唯一标识符）
4. `contact`：生信/运营联系人 JSON 字符串
```json
{"name":"生信和运营的名字","email":"生信和运营的邮箱地址"}
```
5. `cc_emails`：抄送邮箱，支持 JSON 数组字符串或逗号分隔字符串（可选）
6. `verbose`：是否输出详细日志（可选，默认 `true`）

## 压缩包内文件要求
- 必需：`*.SpeFreq.cut`
- 必需：`*.NumFreq.cut`
- 必需：`all.ntcls.xls`（备选匹配：`*.ntcls.xls`）
- 必需：至少一个 `*.species.xls`（备选：`*.species.test.xls`）
- 必需：`*.Result.xls`
- 可选：`*.pos`
- 可选：`.html` 报告文件

## 处理逻辑
- 服务端先保存压缩包到本地：`data/external_uploads/YYYYMMDD/<sample_name>_<task_id>/upload.zip`
- 解压到：`.../extracted/`
- 自动识别样本目录（若解压后仅有一层目录则进入该目录）
- 后续与现有 `run-by-path` 一致：检查文件完整性 -> 执行 survey 判定 -> 入库
- 额外参数会写入 `survey_cases`：`stage_code/contact_name/contact_email/cc_emails_json/archive_path`

## curl 示例
```bash
BASE_URL="http://192.168.20.24:8001"
ZIP_PATH="/tmp/survey_external_test.zip"

curl -X POST "$BASE_URL/api/cases/run-by-archive" \
  -F "archive=@${ZIP_PATH};type=application/zip" \
  -F "stage_code=P1" \
  -F "sample_name=FDSW260016086-2r" \
  -F 'contact={"name":"测试生信","email":"bio@example.com"}' \
  -F 'cc_emails=["ops@example.com","qa@example.com"]' \
  -F "verbose=false"
```

## 响应示例（成功）
```json
{
  "sample_dir": "/data/work/zhurui/survey_rec/data/external_uploads/20260428/FDSW260016086-2r_c3763b3d24fe/extracted/FDSW260016086-2r_CaiXia叶-1",
  "archive_path": "/data/work/zhurui/survey_rec/data/external_uploads/20260428/FDSW260016086-2r_c3763b3d24fe/upload.zip",
  "stage_code": "P1",
  "sample_name": "FDSW260016086-2r",
  "contact": {"name": "测试生信", "email": "bio@example.com"},
  "cc_emails": ["ops@example.com", "qa@example.com"],
  "file_check": {"complete": true, "missing": []},
  "executed": true,
  "message": "压缩包文件齐全，已完成survey判定并入库",
  "case_id": 9
}
```

## 响应示例（文件不全）
```json
{
  "executed": false,
  "message": "输入文件不完整，缺失: *.Result.xls",
  "file_check": {
    "complete": false,
    "missing": ["*.Result.xls"]
  }
}
```
