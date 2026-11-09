#!/bin/sh
MAC=192.168.31.217:8897
LOG=/tmp/mico_aivs_lab/instruction.log
while true; do
  # 确保小爱静音（notifyvol=0），CC 走 mysoftvol 不受影响
  V=$(amixer cget numid=177 2>/dev/null | grep -o 'values=[0-9]*' | head -1 | cut -d= -f2)
  [ -n "$V" ] && [ "$V" != "0" ] && amixer cset numid=177 0 >/dev/null 2>&1

  # 推送 ASR 最终结果
  tail -F "$LOG" 2>/dev/null | while read -r line; do
    case "$line" in
      *'"is_final":true'*)
        (wget -q -O /dev/null --post-data="$line" "http://$MAC/asr" 2>/dev/null) &
        ;;
    esac
  done
  sleep 2
done
