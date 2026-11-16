# 每日英语学习

每天北京时间 09:00 学习三个进阶表达，口语、写作、阅读各一个。输出仍保存到 `D:\English_learning`；最终成果为自包含 UTF-8 HTML，可离线查看配图。

## 原有内容要求

- 选择真实语境中常见、值得辨析的表达，解释含义、语气、搭配、适用场合、常见误用及近义区别。
- 每条两句原创英文例句及中文翻译，明确标注原创。
- 实际打开原文或官方影视材料，核验表达、短引文、来源链接及可定位位置；影视时间戳只在实际核验后填写。
- 优先选择出处和真实配图都可核验的表达；图片来自对应文章或官方画面，脚本下载并内嵌。仍缺图时明确说明，不使用生成图或无关图。
- 去重；以北京时间日期和已有最大编号加一命名 `DayNNN_YYYY-MM-DD.html`。当天已有文件跳过生成，不覆盖；不补齐漏过日期。
- 验证后提交到既有公开仓库 `https://github.com/leeli7383/English-learning`，分支固定 `ai/daily-html-backup`，不强推、不自动合并。推送失败保留本地成果，重试不重新生成。

## 当前脚本入口

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\English_learning\automation\run.ps1
```

依赖 Windows PowerShell、Python 3.10+（标准库，无 pip 依赖）、已登录的 Codex CLI、Git，以及原有进程内代理 `127.0.0.1:7890`。模型和推理强度沿用现有配置，没有降低内容质量、改变模型或改成每周生成。生成调用最多 40 分钟，图片请求有 30 秒超时。

- `-Preview`：真实调用模型并生成 Preview.html，不提交、不推送；仍消耗模型额度。
- `-RefreshIndex`：只扫描历史并重建表达索引，不调用模型、不生成、不推送。
- 日常模型只收到精简生成要求、日期和已有表达列表；不读取历史 HTML、README、进度或历史部署记录。旧 HTML 只在本地建立/更新索引时读取，图片编码不会发给模型。
- 模型输出结构化 JSON，脚本检查三种类别、六句双语例句、来源字段和重复表达，再转义文本并套模板。来源真实性仍靠实际检索核验，字段检查不能替代事实核验。
- 脚本只提交当天文件、表达索引和进度；不会顺手提交其他未跟踪课程。任何已有暂存修改都会使备份停止。

## 自动化管理（已部署）

直接双击项目根目录的 `管理每日英语.cmd`，选择查看状态、立即运行、暂停、恢复、检查环境或打开日志。管理操作本身不调用模型；立即运行在当天已有课程时跳过模型。

Windows 任务名：`EnglishLearningDailyV2`。北京时间每天 09:00，用户已登录时隐藏运行，电池供电允许执行，不补跑关机期间漏过的课程；禁止并发，最长 45 分钟。电脑需开机、登录且代理和网络可用；无需保持 Codex 桌面应用打开，但 Codex CLI 登录须有效。

```powershell
# 查看状态 / 立即运行 / 暂停 / 恢复（修改 Action）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\English_learning\automation\manage.ps1 -Action Status
# 新电脑或路径变化后重新注册
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\English_learning\automation\manage.ps1 -Action Install
```

定时入口为 `automation/scheduled-run.ps1`，复用 `automation/run.ps1` 的互斥锁和原有课程要求。`scheduler.local.json` 保存本机绝对路径，`data/scheduler-status.json` 保存后台执行结果，`logs/scheduler-*.log` 保存日志，三者都不提交。迁移备份保存在 `logs/migration-*`，也不上传 GitHub。

本阶段先部署并验证新任务，再备份移除旧 Windows 任务 `EnglishLearningDaily` 和旧 Codex“每日英语任务”调度；切换的实际验证及清理状态以 PROGRESS.md 为准。保留课程文件、原聊天、其他自动化和已有 Git 分支。

## 文件分工

| 文件 | 用途 |
| --- | --- |
| PROGRESS.md | 当前状态、最近验证、问题与下一步 |
| docs/history.md | 历史部署记录，日常生成不读取 |
| automation/prompt.txt | 只包含内容生成和证据要求 |
| automation/run.ps1 | 互斥锁及统一入口 |
| automation/manage.ps1 | 轻量调度管理、环境验证及任务注册 |
| automation/scheduled-run.ps1 | 隐藏后台运行和状态日志 |
| automation/lesson.py | 去重、日期、模型调用、校验、排版及图片内嵌 |
| automation/sync-github.ps1 | 验证目标分支和远程、阶段提交与推送 |
| data/expressions.json | 从历史课程提取的表达索引；包括旧格式 Day 002 文件 |
| data/state.json | 本机日期、编号、生成及推送状态；运行数据不纳入 Git |
| templates/lesson.html | 固定响应式样式和页面骨架 |
| logs/ | 本机运行诊断，不提交 |

推送失败时检查 `data/state.json` 和日志，修复网络后重跑入口。索引是历史内容的提取，不表示重新核验过旧出处。课程文件为事实来源；运行状态丢失可重建，不依赖聊天历史。修改项目后按阶段更新 PROGRESS.md 并提交。
