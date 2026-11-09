# 任务交接 —— OH2P 接入 CC

**交接时间**：2026-11-09 20:40
**交接原因**：上下文已达 204 轮，需要新会话继续
**当前状态**：**目标基本达成，可用**

---

## 一句话现状

小米智能音箱 Pro（OH2P）已能：
1. **听**你说「小爱同学，今天天气怎么样」（读小爱自己的 ASR 结果）
2. **回答**（CC 用 edge-tts 晓晓音色播报）

**延迟 3-5 秒**，小爱会先说 1-2 秒才被掐断。

---

## 设备事实（现在是活的）

```
IP            192.168.31.89（DHCP，可能变，每次先扫）
Telnet        2323（root，无密码）
固件          1.60.3（从设备自己 dump 的）
启动          /etc/rc.local 里起 telnetd（三重 fallback）
备份          ~/dsh-voice/firmware/backup_new/{system0,system1,data}.bin
系统1         空的（全 0xFF），没有回滚分区
```

**设备可写的只有 `/data` 和 `/tmp`**，`/etc` 是 squashfs 只读。

---

## 现在在跑的东西

### Mac 侧（launchd 自启）

| 服务 | 位置 | 作用 |
|---|---|---|
| `com.cc.listen` | 指向 `~/dsh-voice/cc_listen_push.py` | 读队列 → brain() → speak() |
| `com.cc.remind` | 指向 `~/dsh-voice/remind.py run` | 定时提醒 |

两个都 `RunAtLoad + KeepAlive`，Mac 重启自动回来。

### Mac 侧（手动启动，**重启会丢**）

| 进程 | 端口 | 作用 |
|---|---|---|
| `asr_push_server.py` | 8897 | 接收设备推送 |
| `python3 -m http.server` | 8899 | 提供 TTS mp3（根目录必须是 `/tmp/cc_speak`） |

⚠️ **这两个重启后不会自己回来，需要手动起，或者做成 launchd。**

### 设备侧（**重启会丢**）

| 进程 | 作用 |
|---|---|
| `/tmp/p3.sh` | `tail -F instruction.log` → POST 到 Mac:8897 |

启动命令：
```bash
./dnc.py "start-stop-daemon -S -b -x /bin/sh -- /tmp/p3.sh"
```

---

## 关键文件

```
~/dsh-voice/
  dnc.py                设备命令（可靠版，别用 devtel.py，它输出解析坏了）
  devconn.py            持久 telnet 连接实验（1.3s，不够快，未采用）
  cc_listen_push.py     主守护（推送版）
  speak.py              edge-tts + 音箱播放（带缓存 + 播放验证）
  brief.py              天气（open-meteo）
  remind.py             定时提醒（中文数字解析）
  cc                    统一入口（cc status/weather/say/dev/power）
  README-小爱接入.md    完整使用文档（176 行）
  oh2p-cc-bridge/       开源仓库（已推到 GitHub）
  firmware/backup_new/  固件备份
```

---

## 三个关键发现（别重新踩）

### 1. ASR 结果在 `instruction.log` 的 `RecognizeResult`

```bash
# 正确
grep -o 'RecognizeResult.*' /tmp/mico_aivs_lab/instruction.log | grep '"is_final":true'
# {"payload":{"results":[{"text":"今天天气怎么样"}]}}

# 错误：event.log 的 query 只是发给云端的请求，不是识别结果
```

**必须过滤 `is_final:true`**，否则中间结果会重复响应。

### 2. `amixer numid=5` 是 PDM Gain（麦克风增益），**出厂为 0**

```bash
amixer cget numid=5    # values=0 → 麦克风完全聋
amixer cset numid=5 30 # 修好
```

**这是最容易踩的坑**：服务全在、网络正常、App 能控制，但麦克风增益 0，完全没有唤醒。

### 3. `amixer numid=177` 是 `notifyvol`，`176` 是 `mysoftvol`

- `mysoftvol`（176）= 走 `mediaplayer` 的播放（CC 用）
- `notifyvol`（177）= 小爱的提示音量

**但小爱的主回答**仍绕过这两个，只能靠 `stop` + `kill qplayer/miplayer` 掐断。

---

## 已知的坑（按严重程度）

| # | 坑 | 症状 | 修法 |
|---|---|---|---|
| 1 | `devtel.py` 输出解析失效 | 命令能发但返回空，误判设备无响应 | **用 `dnc.py`**。telnet 有 0xff 协商字节，必须 `errors="replace"` |
| 2 | 旧 `http.server` 占 8899 但根目录错 | 播报 URL 404，音箱一声不出 | `speak.py` 已加探针验证，会杀掉重启 |
| 3 | `busybox stat -c %s` 不支持 | 文件大小永远 0 | 用 `wc -c < file` |
| 4 | `event.log` 覆盖写且 query 长度相同 | size 门控永不触发 | 直接比内容 |
| 5 | `asr` 中途结果 | 同一句话响应多次 | 只取 `is_final:true` |
| 6 | 停 `mico_aivs_lab` 后 `mipns` 不再读麦克风 | 唤醒完全失效 | **重启设备**才能恢复 |
| 7 | 设备 shell 命令超过 80 字符 | 被 telnet 换行截断 | 写脚本用 `wget` 下发 |
| 8 | `(nohup cmd &)` 在 telnet 断连时被杀 | 后台进程消失 | 用 `start-stop-daemon -S -b` |

---

## 下一步优先做什么

完整清单见 `ROADMAP.md`（已推 GitHub）。**最该做的三件**：

### P0-1 降低延迟（3-5s → 目标 1-2s）
- TTS 预生成缓存（常用回答）
- 或换本地 TTS（`say -v Tingting`，<0.3s，牺牲音质）

### P0-2 让小爱别说话
- 现在说 1-2 秒才被掐断
- 尝试从固件里禁用 `mico_aivs_lab` 的 TTS（`instruction.log` 里有 `disabled:["TTS"]` 的先例）

### P0-3 设备端推送开机自启
- `/tmp/p3.sh` 重启就没了
- `/etc` 只读，但可以试 `procd` 从 `/data` 加载

---

## 不能做的事（已验证失败）

| 尝试 | 结果 |
|---|---|
| ALSA 录麦克风原始音频 | 只有 0.05s 缓冲残存，幅度 21/32767 |
| 7 个 FIFO | 全部无写入者 |
| Unix socket | busybox `nc` 不支持 |
| `asr` 接口喂音频文件 | `code: -1` |
| Mac 扬声器播 TTS 触发唤醒 | 不触发（真人声纹才行） |
| `saveenv` / 改 `boot_part` | **绝对不要**（上一台设备就是这么死的） |

---

## 给下一位的话

**目标基本达成了** —— 用户能对着音箱问天气、问时间、设提醒，CC 用晓晓的声音回答。

**剩下的都是打磨**（延迟、抢话、持久化），不是从零开始。

**用户的真实需求**：「躺在床上不想拿 Mac，直接问它」

**别做的事**：
- 别再花时间抢麦克风原始音频（架构上拿不到，见上表）
- 别再怀疑 Type-C 口（用户明确说过不是这个问题）
- 刷机前必须有备份 + 一步一步验证（上一台变砖就是这么来的）

**GitHub 仓库**：https://github.com/Zyrrrrr2k/oh2p-cc-bridge

---

## 交接前最后确认（新会话第一件事）

```bash
# 1. 设备通不通
ping -c2 192.168.31.89 && nc -z -w2 192.168.31.89 2323

# 2. 麦克风增益（最常见的问题）
cd ~/dsh-voice && ./venv/bin/python dnc.py "amixer cget numid=5"

# 3. Mac 侧进程
launchctl list | grep -E "cc\.(listen|remind)"
lsof -ti:8897 >/dev/null && echo "push server OK"
lsof -ti:8899 >/dev/null && echo "http server OK"

# 4. 设备侧推送
./venv/bin/python dnc.py "ps | grep -c '[p]3.sh'"

# 5. 端到端（说完看日志）
tail -f /tmp/cc-listen.log
```
