# OH2P-CC-Bridge

> 小米智能音箱 Pro (OH2P) 接入自建 AI —— **只改设备上 2 个文件**，不装 Rust 客户端，不跑 Docker Server。

在 [open-xiaoai](https://github.com/idootop/open-xiaoai) 的基础上继续迭代：**不劫持音频流，直接读小爱自己的 ASR 结果**。

---

## 和现有方案的区别

| 方案 | 需要 | 音频路径 | 复杂度 |
|---|---|---|---|
| [xiaogpt](https://github.com/yihong0618/xiaogpt) | 小米账号（不刷机） | 云端轮询对话记录 | 低，但延迟 3-5s |
| [open-xiaoai](https://github.com/idootop/open-xiaoai) | 刷机 + Rust client + Server | 劫持麦克风音频流 → WebSocket | 高 |
| [open-xiaoai-bridge](https://github.com/coderzc/open-xiaoai-bridge) | 同上 + Docker | 同上 + 多 AI 后端 | 最高 |
| **本项目** | **只改 shadow + rc.local** | **读 `instruction.log` 的 ASR 结果** | **最低** |

**核心差异**：open-xiaoai 系列要把麦克风原始音频抓出来（这对 OH2P 很难，见下），
本项目**直接用小爱自己的 ASR**，只接管「识别出文字之后」的部分。

---

## 为什么选这条路

OH2P 的麦克风**不通过标准 ALSA 暴露**：

```
PDM 麦克风 → 内核 DSP（aml 私有驱动）→ 私有 socket → mipns-xiaomi → 云端 ASR
```

实测证据：

| 尝试 | 结果 |
|---|---|
| `arecord -D mico_record` | 只有缓冲区残存（0.05s 直流偏置，幅度 21/32767） |
| `hw:0,0` / `hw:0,1` / `hw:0,3` | 全是 dummy 或阻塞 |
| 7 个 FIFO | 全部无写入者 |
| `speech.usock` / `common.usock` | busybox `nc` 不支持 Unix socket |
| `mibrain ai_service {"asr_audio":"..."}` | `code: -1`，不接受外部音频 |

**结论：抓原始音频要逆向 `mipns` 的私有协议（以周计）。**
而小爱本来就在做 ASR，结果就在本地日志里 —— 读它，省掉全部逆向工作。

---

## 架构

```
你说话「小爱同学，今天天气怎么样」
    ↓
小爱 ASR（设备端，需要「小爱同学」唤醒）
    ↓
/tmp/mico_aivs_lab/instruction.log
    → {"name":"RecognizeResult","payload":{"is_final":true,"results":[{"text":"今天天气怎么样"}]}}
    ↓
设备端 push3.sh（tail -F + wget POST，延迟 < 1s）
    ↓
Mac 端 :8897 接收 → /tmp/cc_asr_queue.txt
    ↓
cc_listen_push.py（读本地队列，0.3s 轮询）
    ↓
interrupt_xiaoai()（停小爱播放，避免抢话）
    ↓
brain()（天气 / 时间 / 音量 / 提醒 / 闲聊）
    ↓
speak.py（edge-tts 晓晓 → mp3）
    ↓
HTTP :8899 → ubus mediaplayer player_play_url → 音箱
```

**延迟分解**：ASR 1-2s + 推送 <1s + TTS 1-2s + 播放 1s ≈ **3-5 秒**。

---

## 三个关键发现（现有文档里没有）

### 1. ASR 结果在 `instruction.log`，不在 `event.log`

`event.log` 里的 `payload.query` 是**发给云端的请求**，
`instruction.log` 里的 `RecognizeResult` 才是**云端返回的识别结果**（含 `is_final`）。

```bash
# 错误（只能拿到请求回显）
grep -o '"query":"[^"]*"' /tmp/mico_aivs_lab/event.log

# 正确（拿到最终识别文本）
grep -o 'RecognizeResult.*' /tmp/mico_aivs_lab/instruction.log | grep '"is_final":true'
```

**必须过滤 `is_final:true`**，否则中间结果会导致重复响应。

### 2. `amixer numid=177 notifyvol` 独立控制小爱 TTS

```
numid=176  mysoftvol   ← 走 mediaplayer 的播放（你的 TTS）用这个
numid=177  notifyvol   ← 小爱的 TTS 提示音量
```

小爱的 TTS **不走** `mysoftvol`，所以：

```bash
# 静音小爱，不影响你自己的 TTS
amixer cset numid=177 0

# 你自己的 TTS 音量
amixer cset numid=176 150
```

⚠️ 但实测小爱的主回答仍会绕过 `notifyvol` 直接写 ALSA —— 只能靠停播放器掐断：
```bash
ubus call mediaplayer player_play_operation '{"action":"stop"}'
killall qplayer miplayer
```

### 3. PDM Gain (`numid=5`) 出厂是 0 —— 必须手动调

```bash
amixer cget numid=5
#   : values=0        ← 麦克风完全聋

amixer cset numid=5 30
#   : values=30       ← 才能录到声音
```

**这是最容易踩的坑**：服务全在、网络正常、App 能控制，但麦克风增益是 0，所以完全没有唤醒。

---

## 快速开始

### 前提

设备已刷入带 telnet/SSH 的固件（见 [刷机](#刷机)）。

```bash
# 1. 确认设备可访问
ping 192.168.31.89 && nc -z -w2 192.168.31.89 2323

# 2. 修麦克风增益（必做！）
./dnc.py "amixer cset numid=5 30"

# 3. 静音小爱 TTS（可选）
./dnc.py "amixer cset numid=177 0"

# 4. Mac 端起接收服务
python3 asr_push_server.py &

# 5. 设备端起推送
./dnc.py "wget -q -O /tmp/p3.sh http://MAC:8899/push3.sh && chmod +x /tmp/p3.sh"
./dnc.py "start-stop-daemon -S -b -x /bin/sh -- /tmp/p3.sh"

# 6. Mac 端起守护
launchctl load ~/Library/LaunchAgents/com.cc.listen.plist
```

### 说话

> 小爱同学，今天天气怎么样

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `dnc.py` | 设备命令执行（telnet 直连，处理 0xff 协商字节） |
| `devconn.py` | 持久 telnet 连接（未使用，因延迟仍达 1.3s） |
| `asr_push_server.py` | Mac 端 :8897 接收设备推送 |
| `push3.sh` | 设备端：tail 日志 + POST + 音量 watchdog |
| `cc_listen_push.py` | Mac 端守护：读队列 → brain → speak |
| `speak.py` | edge-tts + 音箱播放（带缓存与播放验证） |
| `brief.py` | 天气（open-meteo） |
| `remind.py` | 定时提醒（launchd + 中文时间解析） |

---

## 踩过的坑

| # | 坑 | 症状 | 修法 |
|---|---|---|---|
| 1 | `busybox stat -c %s` 不支持 | 文件大小永远 0 | 用 `wc -c < file` |
| 2 | `event.log` 覆盖写且长度相同 | size 门控永不触发 | 直接比内容，别靠大小 |
| 3 | 旧 `http.server` 占端口但根目录错 | 播报 URL 404，音箱一声不出 | 探针文件验证目录 |
| 4 | `player_get_play_status` 不稳 | 误报播放失败 | 改验 URL 可达性 |
| 5 | Unicode 转义 `\u73b0\u5728` | 中文匹配全失败 | `json.loads('"'+s+'"')` |
| 6 | `asr` 中途结果 | 同一句话响应多次 | 只取 `is_final:true` |
| 7 | 停 `mico_aivs_lab` 后 `mipns` 不再读麦克风 | 唤醒失效 | **重启设备**恢复 |
| 8 | PDM Gain = 0 | 完全听不到 | `amixer cset numid=5 30` |

---

## 刷机

固件必须**从这台设备自己 dump 的 system0** 改出来，**不能跨版本**。

```bash
# 1. 备份（bootrom 模式，VID 0x1B8E）
macos/update identify 7
macos/update partition system0 read backup/system0.bin

# 2. 解包 → 只改两处
unsquashfs -d rootfs system0.bin
#   etc/shadow         改 root 密码哈希
#   etc/init.d/boot    echo 1 > /data/ssh_en

# 3. 打包（参数必须与出厂一致）
mksquashfs rootfs out.squashfs -comp xz -b 131072 -all-root -no-xattrs -noappend

# 4. 刷
macos/update partition system0 out.squashfs
```

**红线**：不碰 `boot_part` / 不 `saveenv` / 不擦 `/data`。
新机 `system1` 是空的（全 0xFF），**没有回滚分区**。

---

## 未解决的问题

- **小爱主回答仍会先说 1-2 秒**才被掐断（ASR 需要时间出结果，无法更早）
- **如果要彻底禁用小爱 TTS**，需要改固件（`mico_aivs_lab` 里的 TTS 开关）
- **唤醒词固定是「小爱同学」**，要自定义需要 `open-xiaoai-bridge` 那种原生客户端

## 致谢

- [open-xiaoai](https://github.com/idootop/open-xiaoai) —— 刷机方法与设备探索的起点
- [xiaogpt](https://github.com/yihong0618/xiaogpt) —— 最早的可行性证明
- [open-xiaoai-bridge](https://github.com/coderzc/open-xiaoai-bridge) —— 功能完整度的参考

## License

MIT
