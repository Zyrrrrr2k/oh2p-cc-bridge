#!/usr/bin/env python3
"""CC 主动播报：抓天气 + 生成语音 + 音箱播放。
用法: brief.py [weather|morning|evening]
"""
import sys, os, json, subprocess, urllib.request

VENV = os.path.expanduser("~/dsh-voice/venv/bin/python")
SPEAK = os.path.expanduser("~/dsh-voice/speak.py")
CITY = os.environ.get("JJ_CITY", "温州")
LAT = os.environ.get("JJ_LAT", "27.99")
LON = os.environ.get("JJ_LON", "120.70")

WMO = {
    0:"晴", 1:"晴间多云", 2:"多云", 3:"阴", 45:"有雾", 48:"有雾",
    51:"小毛雨", 53:"毛毛雨", 55:"密毛雨",
    61:"小雨", 63:"中雨", 65:"大雨",
    66:"冻雨", 67:"强冻雨",
    71:"小雪", 73:"中雪", 75:"大雪", 77:"雪粒",
    80:"阵雨", 81:"强阵雨", 82:"暴雨",
    85:"阵雪", 86:"强阵雪",
    95:"雷阵雨", 96:"雷阵雨伴冰雹", 99:"强雷暴伴冰雹",
}


def weather_text():
    url = ("https://api.open-meteo.com/v1/forecast"
           "?latitude=%s&longitude=%s"
           "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
           "precipitation,weather_code,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min,"
           "precipitation_probability_max,weather_code"
           "&timezone=Asia%%2FShanghai&forecast_days=2"
           % (LAT, LON))
    req = urllib.request.Request(url, headers={"User-Agent": "cc-brief/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())

    cur = d["current"]
    day = d["daily"]
    t = cur["temperature_2m"]
    feels = cur["apparent_temperature"]
    hum = cur["relative_humidity_2m"]
    code = cur["weather_code"]
    desc = WMO.get(code, "未知")
    hi = day["temperature_2m_max"][0]
    lo = day["temperature_2m_min"][0]
    rain = day["precipitation_probability_max"][0]
    code_t = day["weather_code"][1]

    parts = ["%s现在%s，%s度" % (CITY, desc, round(t))]
    if abs(feels - t) >= 3:
        parts.append("体感%s度" % round(feels))
    parts.append("今天%s到%s度" % (round(lo), round(hi)))
    if rain >= 50:
        parts.append("降水概率%s%%，出门记得带伞" % rain)
    elif rain >= 25:
        parts.append("降水概率%s%%" % rain)
    if hum >= 85:
        parts.append("湿度%s%%，有点闷" % hum)
    if code_t in (61,63,65,80,81,82,95,96,99):
        parts.append("明天可能下雨")
    return "，".join(parts) + "。"


def speak(text):
    r = subprocess.run([VENV, SPEAK, text, "xiaoxiao"],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0, r.stdout.strip()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "weather"
    try:
        if mode in ("weather", "morning", "evening"):
            text = weather_text()
        else:
            text = mode
    except Exception as e:
        print("✗ 获取天气失败:", type(e).__name__, str(e)[:120])
        return 1

    print("  播报内容:", text)
    ok, out = speak(text)
    if ok:
        print("  ✓ 已从音箱播出")
        return 0
    print("  ✗ 播放失败:", out[-200:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
