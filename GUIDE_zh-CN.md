# PaperTalkthrough · 边听边聊 使用指南

**论文读给你听，你也可以随时插话。**

- 🎧 **全程听**：靠在椅子上，让它用自然的声音把整篇论文读给你听。
- 👀 **边听边看**：读到哪一句，哪一句就亮起来。可以看整理好的文字，也可以看 PDF 原页面。点任意一句就从那里开始读。
- 📞 **随时打电话**：读到一半按 **Call**，想聊什么都行："等等，这是什么意思？"、"这和上一篇论文有什么不同？"、"帮我查一下这个"。读过整篇论文的 AI 会开口回答你。说一声"继续"，它就从刚才停下的地方接着读。
- 🖍️ **让 AI 帮你标注**："把这句标成绿色"、"在这句旁边记一下：问问导师"。当然，你也可以自己动手高亮、写笔记。
- 📄 **导出 PDF**：所有高亮和笔记都会保存在导出的 PDF 里，用任何 PDF 阅读器都能打开。

## 需要准备什么

- 一台 **Windows 或 Mac** 电脑，大约 1 GB 空闲空间
- **Python 3.10、3.11 或 3.12**（推荐 3.12）
- **Google Chrome** 或 **Microsoft Edge** 浏览器（用语音和 AI 对话时需要）
- 一个 AI 服务的 **API key**，要支持 "OpenAI 兼容" 格式。大多数服务都支持：OpenAI、Anthropic（Claude）、Google Gemini、OpenRouter、DeepSeek，以及很多学校或公司提供的 AI 网关。只朗读不提问的话，不需要 key。

## 安装（大约 15 分钟，只需做一次）

### 1. 下载 PaperTalkthrough

在 GitHub 项目页面点绿色的 **Code** 按钮 → **Download ZIP**，然后解压到一个好找的地方，比如"文档"文件夹。

> **Windows**：右键 ZIP 文件 → **全部解压缩**。解压后有时会多套一层文件夹，要用**里面那层**，也就是能直接看到 `server.py` 的那个文件夹。

### 2. 安装 Python

去 [python.org/downloads](https://www.python.org/downloads/) 下载 **Python 3.12**。

- **Windows**：安装程序第一个界面的最下面，**一定要勾选 "Add python.exe to PATH"**，再点 **Install Now**。如果最新的 3.12 版本只有源代码，就往前找一个带 **Windows installer (64-bit)** 的 3.12 版本。
- **Mac**：正常安装即可。

### 3. 在 PaperTalkthrough 文件夹里打开命令窗口

- **Windows**：在文件资源管理器里打开 PaperTalkthrough 文件夹，点一下顶部的地址栏，输入 `cmd`，按回车。弹出的黑色窗口就已经在这个文件夹里了。
- **Mac**：打开"**终端**"，输入 `cd `（cd 后面有一个空格），把 PaperTalkthrough 文件夹拖进终端窗口，按回车。

确认位置对不对：输入 `dir`（Windows）或 `ls`（Mac）按回车，列表里应该能看到 `server.py`。

> 下面的命令里，Windows 用 `py`；**Mac 请把 `py` 换成 `python3`**。

### 4. 安装需要的组件

```
py -m pip install -r requirements.txt
```

要等几分钟。最后出现"pip 有新版本"的提示可以忽略。

### 5. 下载语音模型（约 350 MB）

```
py download_models.py
```

等到显示 `Voice model ready.` 就好了。

### 6. 填写 API key

把 `.env.example` 复制一份，命名为 `.env`：

- **Windows**：先运行 `copy .env.example .env`，再运行 `notepad .env`
- **Mac**：先运行 `cp .env.example .env`，再运行 `open -e .env`

在打开的文件里填好这三行，然后保存：

```
OPENAI_BASE_URL=   你的 AI 服务的地址（文件里列了常见服务的地址）
OPENAI_API_KEY=    你的 key
MODEL=             要用的模型名
```

等号两边不要加空格，也不要加引号。按 Ctrl+S（Mac 是 Cmd+S）保存后关闭。

> **`.env` 文件里有你的 key，千万不要发给别人，也不要上传到任何地方。**

### 7. 检查 key 能不能用

```
py check_gateway.py
```

它会列出你的 key 能用的模型，并让 AI 回复一句测试。看到 `All good` 就说明成功了。不成功的话，检查一下地址、key，以及 `MODEL` 是否和列出的某个模型名**完全一致**。

**选哪个模型？** 选小而快的，名字里通常带 "mini"、"flash" 或 "haiku"。回答开始得快，打电话才自然，而且便宜很多。不要选大型的"推理"模型，它们回答前要想很久，电话里会冷场。

### 8. 启动

```
py server.py
```

浏览器会自动打开 **http://localhost:8000**。如果没有自动打开，就自己在 Chrome 或 Edge 里输入这个地址。

**使用期间，这个命令窗口不要关**，关掉程序就停了。

**以后每次启动**：直接双击 `start-windows.bat`（Windows）或 `start-mac.command`（Mac）。如果 Mac 不让打开这个文件，就用终端：进入文件夹后运行 `python3 server.py`。

## 怎么用

1. 点 **Open a PDF** 选一篇论文。必须是能选中文字的 PDF；扫描版（每页都是图片）读不了。
2. 按 **▶**（或空格键）开始朗读。
3. 按 **Call** 直接说话。第一次会问能不能用麦克风，点"允许"。说完后停顿大约两秒，AI 就会用语音回答。
4. 说 **"move on"** / **"继续"**，或者点 **Hang up & keep reading**，就从你打断的那一句接着读。

**通话中可以这样说：**

- "move on" / "继续"：挂断，接着读
- "repeat that" / "再读一遍"：重读你打断时的那一句
- "go back" / "上一句"：退回一句
- "highlight 'design-based research' in blue"（把这几个词标成蓝色）
- "add a note to this sentence: ask the professor about this"（在这句旁边记笔记）
- "look up what Cohen's kappa means"（上网查一下）
- "is this paper part of a bigger project?"（这篇论文是不是某个大项目的一部分？）

**用鼠标：**

- **单击一个句子**：从这里读、高亮这句，或者就这句提问。
- **拖动选中文字**：高亮、写笔记，或者就这几个词提问。
- **点已有的高亮**：改颜色、编辑笔记或删除。
- **Page view**（右上角）：在纯文字和 PDF 原始页面之间切换。
- **Export PDF**（右上角）：下载一份带高亮和笔记的 PDF。
- **Skip**（底部栏）：选择朗读时跳过哪些内容：Citations（引用）、Captions（图表标题）、Tables（表格）、Code（代码）、Small print（脚注小字）。
- **Interrupt by talking**（Call 按钮旁边）：开启后，AI 说话时你可以直接开口打断它。最好戴耳机，否则 AI 可能听到自己从音箱里发出的声音。

阅读进度、高亮、笔记和对话记录都会自动保存，每篇文章分开保存。

## 在手机上用（可选）

所有的工作都在电脑上完成，手机上显示一个精简页面，可以朗读、打电话，并从上次的位置继续。这里要用到 **Tailscale**，一个免费工具，可以把你自己的设备私密地连在一起。只有登录了你的 Tailscale 账号的设备才能打开这个页面。

1. 电脑上安装 **Tailscale**（[tailscale.com/download](https://tailscale.com/download)），手机上也安装（App Store / Google Play）。**两边用同一个私人账号登录**。
   > 如果用学校或公司邮箱登录，同一机构的其他人可能会进入同一个网络。用私人账号（Google、Apple、GitHub）更安全。
2. 电脑上照常启动 PaperTalkthrough。
3. **另开一个新的**命令窗口，运行：
   ```
   tailscale serve --bg 8000
   ```
   - 如果显示一个链接，说 Serve 没有开启：打开这个链接，开启 **HTTPS certificates**，**不要勾选 Tailscale Funnel**（Funnel 会把你的电脑开放给整个互联网）。然后再运行一次上面的命令。
   - 如果 Windows 提示找不到 tailscale 命令，改用：`"C:\Program Files\Tailscale\tailscale.exe" serve --bg 8000`
4. 它会显示一个网址，类似 `https://你的电脑名.xxxx.ts.net/`。在手机上确认 Tailscale 已连接，用浏览器打开这个网址，提示使用麦克风时点"允许"。iPhone 上可以在 Safari 里点"**分享 → 添加到主屏幕**"，像 App 一样打开。

这个设置只需要做一次。之后：

- 电脑要**开着、不能睡眠**。在电源设置里把插电时的"睡眠"设为"从不"，屏幕可以照常关闭。
- 电脑上的 PaperTalkthrough 要**在运行**。
- 手机听的时候屏幕要亮着。手机上点一下状态栏（"Speaking — tap here to interrupt"）就能打断 AI。

**可选：Windows 开机自动启动 PaperTalkthrough。** 按 Win + R，输入 `shell:startup` 回车，把 `start-windows.bat` 的快捷方式放进打开的文件夹。

## 费用和隐私

- **朗读**完全在你的电脑上进行，免费。
- **AI 对话**按你的 AI 服务收费。每次提问会发送文章内容和最近的对话。用小模型的话，一篇普通论文每问一次通常只要几美分甚至更少。很多服务商会缓存文章内容，连续追问会更便宜。命令窗口里会显示每次回答用了多少 token。
- **会离开你电脑的内容**：文章文字和你的问题，会发给你选的 AI 服务。你说的话由浏览器的语音识别转成文字，Chrome 用的是 Google 的服务器。搜索请求会发给上面提到的搜索服务。
- **只留在你电脑上的内容**：PDF、笔记、高亮和对话记录，都在 `library` 文件夹里。

## 常见问题

| 问题 | 解决方法 |
|---|---|
| `'pip' is not recognized` 或 `'python' is not recognized`（Windows） | 用 `py -m pip ...` 和 `py ...`。如果 `py` 也找不到，重新安装 Python，并勾选 **"Add python.exe to PATH"**，然后重新打开命令窗口。 |
| `Python was not found; run without arguments to install from the Microsoft Store` | 同上，用 `py` 代替 `python`。 |
| `Could not open requirements file` | 命令窗口不在 PaperTalkthrough 文件夹里，见第 3 步。 |
| `Fill in OPENAI_BASE_URL and OPENAI_API_KEY` | `.env` 文件不存在或没保存。Windows 上检查它是不是被存成了 `.env.txt`：运行 `dir /a` 查看，必要时运行 `ren .env.txt .env` 改名。 |
| 提示语音模型文件缺失 | 再运行一次 `py download_models.py`。 |
| AI 不回答或显示报错 | 运行 `py check_gateway.py`，按它提示的问题修改。 |
| 麦克风听不到我说话 | 用 Chrome 或 Edge，允许使用麦克风（地址栏里的图标），并且让 PaperTalkthrough 的标签页保持在前台：浏览器会暂停后台标签页的语音识别。 |
| 打开 PDF 时显示 "Failed to fetch" | 程序停止了，看命令窗口里的报错信息。 |
| 打开 PDF 后没有文字 | 很可能是扫描版 PDF（每页是图片），需要先做文字识别（OCR）。 |
| 双栏论文的朗读顺序乱了 | 有些 PDF 内部的文字顺序比较特殊，可以在 GitHub 上提 issue 并附上论文。 |
| 更新文件后没有变化 | 重启程序，然后在浏览器里按 Ctrl+F5（Mac 是 Cmd+Shift+R）。 |

## 文件说明

| 文件 | 作用 |
|---|---|
| `server.py` | 主程序：读 PDF、生成语音、和 AI 对话 |
| `static/index.html` | 电脑版页面 |
| `static/mobile.html` | 手机版页面 |
| `.env.example` | 设置模板，复制成 `.env` 后填写 |
| `check_gateway.py` | 检查 API key、列出可用模型 |
| `download_models.py` | 下载语音模型 |
| `start-windows.bat`、`start-mac.command` | 双击启动 |
