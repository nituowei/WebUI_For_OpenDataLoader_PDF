# WebUI For OpenDataLoader PDF

A native WebUI for macOS to control the conversion process of OpenDataLoader PDF.

一个面向 macOS 的本地 WebUI，用来控制 OpenDataLoader PDF 的转换流程。

## 功能

- 静态 H5 前端，后端只提供本地 API。
- 一键启动/停止可选的 OpenDataLoader hybrid daemon。
- 一键打开 macOS 文件选择器，选择一个或多个 PDF 文件。
- 一键打开 macOS folder picker，设置默认输出目录。
- 支持 JSON、Markdown、HTML、Text、PDF、Tagged PDF 输出格式。
- 默认不导出图片，生成纯文本/Markdown/JSON 时不会额外产生 PNG；需要图片时可在界面切换。
- 支持依赖检查、转换日志、任务状态轮询。
- 页面可关闭 WebUI 主进程，也提供启动/关闭脚本管理 8787 端口。

## 系统要求

- macOS
- Python 3.10+
- Java 11+

当前 OpenDataLoader 文档要求 Java 11+ 和 Python 3.10+。如果 `java -version` 不可用，可以安装 Temurin：

```bash
brew install --cask temurin
```

如果不想输入管理员密码，也可以使用 Homebrew formula：

```bash
brew install openjdk
```

本项目的 `run.sh` 会自动识别 `/opt/homebrew/opt/openjdk`。

## 安装

```bash
git clone https://github.com/nituowei/WebUI_For_OpenDataLoader_PDF.git
cd WebUI_For_OpenDataLoader_PDF
./setup.sh
```

`setup.sh` 会安装 `opendataloader-pdf[hybrid]`，用于支持基础转换和 hybrid daemon。

## 启动

```bash
./run.sh
```

然后打开：

```text
http://127.0.0.1:8787
```

更推荐日常使用这两个脚本：

```bash
./start-webui.sh
./stop-webui.sh
```

`start-webui.sh` 会在后台启动 8787 服务并用默认浏览器打开 WebUI。`stop-webui.sh` 会关闭 8787 主进程。页面里的“关闭 WebUI”按钮也可以关闭当前主进程；但网页无法启动一个尚未运行的本地服务，因为网页本身依赖 8787 服务才能加载。

## 移动目录

项目可以移动到任意目录，只要保持项目内部文件结构不变即可。移动后建议重新运行：

```bash
./setup.sh
./start-webui.sh
```

不要提交或复用旧的 `.venv/`，Python 虚拟环境通常包含本机绝对路径，移动目录后重新安装更稳。

## 设计建议

- 普通转换不建议常驻 daemon：OpenDataLoader 的基础 Python/CLI 转换会按任务启动 JVM，完成后退出，更省资源。
- daemon 更适合 hybrid 模式：如果需要 OCR/复杂版面后端，再用界面启动 hybrid daemon，用完一键停止。
- 输出目录建议固定：例如 `~/Documents/ODL Output`，这样后续接入 RAG、搜索索引或归档脚本更稳定。
- 后续可以增加“最近任务列表”和“格式预设”，例如“RAG Markdown only”“审阅 HTML+JSON”“归档 Tagged PDF”。
- 浏览器安全限制不允许网页直接读取任意本地绝对路径，所以本项目由本地后端触发 macOS 原生文件/目录选择器。
