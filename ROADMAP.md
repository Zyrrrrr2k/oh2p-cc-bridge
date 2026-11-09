# 优化路线图

按「投入产出比」排序。

## P0 —— 影响可用性，优先

### 1. 降低延迟（现在 3-5 秒）
当前分解：ASR 1-2s + 推送 <1s + TTS 生成 1-2s + 播放启动 1s

- [ ] **TTS 预生成**：常用回答（天气/时间/问候）提前生成缓存，命中就省 1-2 秒
- [ ] **流式播放**：TTS 边生成边播（edge-tts 支持 chunk），省 1 秒
- [ ] **本地 TTS**：`say -v Tingting` 或 Piper（离线，<0.3 秒），牺牲音质换速度

### 2. 小爱抢话（现在会说 1-2 秒才被掐断）
- [ ] **改固件禁用小爱 TTS**：在 `mico_aivs_lab` 里找 TTS 开关，或从 `instruction.log` 的
      `RequestControl.payload.disabled=["TTS"]` 反推触发方式
- [ ] **更快的掐断**：现在靠 stop + kill，可以试 `SIGSTOP` 小爱的播放进程

### 3. 设备端推送丢失（重启后 push3.sh 没了）
- [ ] **开机自启**：`/etc/rc.local` 只读，但 `/data` 可写 —— 可以让 `mico_ai_crontab` 或
      `procd` 从 `/data` 加载启动脚本
- [ ] **或改用固件内置**：把 push 逻辑打进 system0（需要重新刷机）

### 4. PDM Gain 不持久（重启后可能变回 0）
- [ ] 已实测重启后仍是 30，但不确定是 `/data` 持久还是巧合 —— 需要验证
- [ ] 保险做法：push3.sh 里加 `amixer cset numid=5 30` 的 watchdog

## P1 —— 提升体验

### 5. 换自定义唤醒词
- [ ] 移植 [`open-xiaoai-bridge`](https://github.com/coderzc/open-xiaoai-bridge) 的客户端
      它支持自定义唤醒词、连续对话、音色克隆、流式播放
- [ ] 代价：要装 Rust client + Docker Server，比现在的方案重很多

### 6. 接真正的 LLM（现在是规则版 brain）
- [ ] `cc_listen_push.py` 的 `brain()` 换成 LLM 调用
- [ ] 需要 API key（DeepSeek / OpenAI / 本地 Ollama）
- [ ] 保留规则版做 fallback（LLM 失败时仍能答天气时间）

### 7. 连续对话
- [ ] 唤醒后保持 N 秒监听（不用每次说「小爱同学」）
- [ ] 小爱的 `continue_dialog` 相关指令里有线索：
      `instruction.log` 的 `DialogState.payload.continuous_dialog`

### 8. 更多意图
- [ ] 音乐播放（`mediaplayer player_play_music`）
- [ ] 闹钟（`alarm` ubus 服务）
- [ ] 音量细调（现在只有大/小两档）
- [ ] 设备状态查询（"你还剩多少空间"）

## P2 —— 长期

### 9. 声音克隆
- [ ] GPT-SoVITS / CosyVoice，用你自己的声音说话
- [ ] 需要 GPU 或等更小的模型

### 10. 多房间
- [ ] 如果有多台 OH2P，做一个统一入口

## 已知的硬限制

| 限制 | 原因 | 能否突破 |
|---|---|---|
| 唤醒词必须是「小爱同学」 | 小爱的唤醒模型是闭源的 | 只能换 client（P1-5） |
| 麦克风原始音频拿不到 | PDM → DSP → 私有 socket | 只能逆向 mipns |
| 小爱会先说 1-2 秒 | ASR 需要时间出结果 | 只能禁 TTS（P0-2） |
| `asr` 接口不接受外部音频 | 设备限制 | 无解 |
