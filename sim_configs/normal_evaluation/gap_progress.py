#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gap_progress.py — run_267_gap.sh(GAP 벤치마크) 실시간 진행 모니터.

results/normal_evaluation 아래의 GAP 실험(2/6/7)에 대해
  - 각 작업이 현재 몇 M instruction까지 진행됐는지
  - 전체 300M(warmup 50M + sim 250M) 대비 진행 %
  - 현재까지 경과시간(실제 wall-clock)과 예상 남은시간(ETA)
를 모든 벤치마크에 대해 일정 간격(기본 10초)으로 갱신해 보여준다.

작업 목록은 run_267_gap.sh / run_common.sh / run_gap_common.sh 를 그대로 읽어
산출하므로 실행 스크립트를 바꾸면 자동으로 따라간다.

사용:
    python3 gap_progress.py                 # 10초마다 갱신
    python3 gap_progress.py -i 5            # 5초 간격
    python3 gap_progress.py --once         # 한 번만 출력하고 종료
    python3 gap_progress.py --all          # 완료/대기 작업까지 전부 나열
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAMPSIM_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
CONFIG_BASE = SCRIPT_DIR
RESULTS_BASE = os.path.join(CHAMPSIM_DIR, "results", "normal_evaluation")
RUNNER = os.path.join(SCRIPT_DIR, "run_267_gap.sh")
RUN_COMMON = os.path.join(SCRIPT_DIR, "run_common.sh")
RUN_GAP_COMMON = os.path.join(SCRIPT_DIR, "run_gap_common.sh")

# ---------------------------------------------------------------------------
# 정규식
# ---------------------------------------------------------------------------
# 완전한 heartbeat 한 줄 (instr + 시뮬레이션 경과시간 둘 다 있는 줄)
RE_HEARTBEAT = re.compile(
    r"Heartbeat CPU \d+ instructions:\s*(\d+).*?"
    r"\(Simulation time:\s*(\d+)\s*hr\s*(\d+)\s*min\s*(\d+)\s*sec\)"
)
# 완료 줄의 총 소요시간 (heartbeat 없는 작업의 ETA 폴백용)
RE_COMPLETE_TIME = re.compile(
    r"Simulation complete.*?\(Simulation time:\s*(\d+)\s*hr\s*(\d+)\s*min\s*(\d+)\s*sec\)"
)
RE_QUEUE = re.compile(r'queue_experiment\s+"([^"]+)"\s+"([^"]+)"')
RE_RUN = re.compile(r'run_experiment\s+"([^"]+)"\s+"([^"]+)"')
RE_EXE = re.compile(r'"executable_name"\s*:\s*"([^"]+)"')
# run_gap_common.sh 의 주석 해제된 트레이스 줄
RE_TRACE = re.compile(r'^\s*"\$\{TRACE_DIR\}/(gap/[^"]+)"')
RE_WARMUP = re.compile(r"^\s*WARMUP\s*=\s*(\d+)", re.M)
RE_SIM = re.compile(r"^\s*SIM\s*=\s*(\d+)", re.M)

# 기본값 (run_common.sh 파싱 실패 시 fallback)
DEFAULT_WARMUP = 50_000_000
DEFAULT_SIM = 250_000_000

# ---------------------------------------------------------------------------
# 색상
# ---------------------------------------------------------------------------
USE_COLOR = sys.stdout.isatty()


def c(code, s):
    if not USE_COLOR:
        return s
    return f"\033[{code}m{s}\033[0m"


GREEN = lambda s: c("32", s)
YELLOW = lambda s: c("33", s)
RED = lambda s: c("31", s)
CYAN = lambda s: c("36", s)
GREY = lambda s: c("90", s)
BOLD = lambda s: c("1", s)


# ---------------------------------------------------------------------------
# 설정 파싱
# ---------------------------------------------------------------------------
def read_text(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def parse_totals():
    """run_common.sh 에서 WARMUP / SIM 값을 읽는다."""
    txt = read_text(RUN_COMMON)
    w = RE_WARMUP.search(txt)
    s = RE_SIM.search(txt)
    warmup = int(w.group(1)) if w else DEFAULT_WARMUP
    sim = int(s.group(1)) if s else DEFAULT_SIM
    return warmup, sim


def parse_experiments():
    """run_267_gap.sh 의 queue_experiment / run_experiment 줄에서
    (config_dir, result_tag) 쌍을 뽑는다."""
    txt = read_text(RUNNER)
    pairs = RE_QUEUE.findall(txt) + RE_RUN.findall(txt)
    # 중복 제거(순서 보존)
    seen, out = set(), []
    for cfg, tag in pairs:
        if (cfg, tag) not in seen:
            seen.add((cfg, tag))
            out.append((cfg, tag))
    return out


def parse_active_traces():
    """run_gap_common.sh 에서 주석 해제된 GAP 트레이스의 basename 목록."""
    traces = []
    for line in read_text(RUN_GAP_COMMON).splitlines():
        m = RE_TRACE.match(line)
        if m:
            traces.append(os.path.basename(m.group(1)))  # 예: bc-3.trace.gz
    return traces


def parse_exe_name(config_path):
    m = RE_EXE.search(read_text(config_path))
    return m.group(1) if m else None


def build_jobs(experiments, traces):
    """예상 작업 전체를 산출.
    반환: jobs = [ {tag, exp_label, binary, trace, path}, ... ]
          bin2tag = {binary: result_tag}
    출력 파일 이름 규칙(run_common.sh와 동일): <binary>_<trace_basename>.txt
    """
    jobs = []
    bin2tag = {}
    for cfg_dir, tag in experiments:
        # run_common.sh 와 동일하게 재귀적으로(find -name '*.json') 찾는다.
        cfg_glob = os.path.join(CONFIG_BASE, cfg_dir, "**", "*.json")
        configs = sorted(glob.glob(cfg_glob, recursive=True))
        for cfg in configs:
            binary = parse_exe_name(cfg)
            if not binary:
                continue
            bin2tag[binary] = tag
            for tr in traces:
                out = os.path.join(RESULTS_BASE, tag, f"{binary}_{tr}.txt")
                jobs.append(
                    dict(tag=tag, exp_label=cfg_dir, binary=binary, trace=tr, path=out)
                )
    return jobs, bin2tag


# ---------------------------------------------------------------------------
# 실행 중인 프로세스 매핑
# ---------------------------------------------------------------------------
def get_running():
    """현재 실행 중인 ChampSim 프로세스를 (binary, trace_basename) -> (pid, etimes초) 로."""
    running = {}
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid=,etimes=,args="], text=True, errors="replace"
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return running
    for line in out.splitlines():
        if "--warmup-instructions" not in line or "/bin/" not in line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            etimes = int(parts[1])
        except ValueError:
            continue
        args = parts[2].split()
        binary = trace = None
        for tok in args:
            if "/bin/" in tok:
                binary = os.path.basename(tok)
            elif tok.endswith(".gz") or tok.endswith(".xz"):
                trace = os.path.basename(tok)
        if binary and trace:
            running[(binary, trace)] = (pid, etimes)
    return running


# ---------------------------------------------------------------------------
# 출력 파일 파싱
# ---------------------------------------------------------------------------
def read_tail(path, n):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def parse_heartbeats(tail):
    """tail 텍스트에서 (instr, 경과초) 쌍들을 순서대로 반환."""
    beats = []
    for m in RE_HEARTBEAT.finditer(tail):
        instr = int(m.group(1))
        secs = int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4))
        beats.append((instr, secs))
    return beats


def analyze_file(path):
    """출력 파일 상태 분석.
    반환 dict: exists, complete, panic, beats(list), last_instr, last_simsec
    """
    info = dict(exists=False, complete=False, panic=False,
                beats=[], last_instr=0, last_simsec=0, mtime=0.0, dur=None)
    if not os.path.exists(path):
        return info
    info["exists"] = True
    try:
        info["mtime"] = os.path.getmtime(path)
    except OSError:
        info["mtime"] = 0.0
    tail = read_tail(path, 16384)
    if "Simulation complete" in tail:
        info["complete"] = True
        m = RE_COMPLETE_TIME.search(tail)
        if m:
            info["dur"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    # panic: deadlock 감지로 IPC 붕괴 (무한 출력). 완료가 아니면서 panic 줄이 있으면 패닉.
    if not info["complete"] and "panic" in tail:
        info["panic"] = True
    beats = parse_heartbeats(tail)
    # panic 스팸(수천 줄)이나 큰 파일이면 마지막 heartbeat가 16KB tail 밖으로 밀려난다.
    # 그 경우 파일 전체를 훑어 진짜 마지막 heartbeat(= 멈추기 전 도달 지점)를 찾는다.
    if not beats and not info["complete"]:
        try:
            big = os.path.getsize(path) > 16384
        except OSError:
            big = False
        if big:
            beats = parse_heartbeats(read_text(path))
    info["beats"] = beats
    if beats:
        info["last_instr"] = beats[-1][0]
        info["last_simsec"] = beats[-1][1]
    return info


# ---------------------------------------------------------------------------
# 진행률 / ETA 계산
# ---------------------------------------------------------------------------
def compute_eta(beats, last_instr, elapsed, warmup, total):
    """남은 예상시간(초). 정상/패닉/멈춤 모든 상태에 일관 적용.

    속도 기준 우선순위:
      (1) sim 단계 평균 속도 — warmup(50M) 종료 직후 첫 heartbeat를 기준점으로
          (현재instr - 기준instr) / (현재경과 - 기준시각).
          워밍업이 빠르고 sim이 느린 차이를 제거하고, panic처럼 heartbeat가
          끊겨도 '지금까지의 평균 진행속도'로 추정할 수 있다.
      (2) 폴백 — 전체 평균 (last_instr / elapsed).
    panic은 IPC가 붕괴해 평균 속도가 극히 낮으므로 ETA가 며칠~수십일로
    크게 나오며, 이는 '사실상 안 끝남'을 그대로 반영한다.
    """
    remaining = total - last_instr
    if remaining <= 0:
        return 0
    if not elapsed or elapsed <= 0:
        return None
    rate = None
    if last_instr > warmup and beats:
        anchor = next((b for b in beats if b[0] >= warmup), None)
        if anchor:
            sim_done = last_instr - anchor[0]
            sim_elapsed = elapsed - anchor[1]
            if sim_done > 0 and sim_elapsed > 0:
                rate = sim_done / sim_elapsed
    if rate is None and last_instr > 0:
        rate = last_instr / elapsed
    if not rate or rate <= 0:
        return None
    return remaining / rate


def fmt_dur(seconds):
    if seconds is None:
        return "?"
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d > 0:
        return f"{d}d{h:02d}h"
    if h > 0:
        return f"{h}h{m:02d}m"
    if m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def fmt_m(instr):
    return f"{instr / 1_000_000:.0f}M"


def bar(frac, width=14):
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


# ---------------------------------------------------------------------------
# 메인 한 회 렌더링
# ---------------------------------------------------------------------------
def render(jobs, bin2tag, total_instr, warmup, sim, show_all, stall_min, interval):
    running = get_running()
    now_ts = time.time()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # tag 순서(첫 등장 순)
    tag_order = []
    for j in jobs:
        if j["tag"] not in tag_order:
            tag_order.append(j["tag"])

    per_tag = {t: dict(total=0, done=0, running=0, pending=0,
                       panic=0, failed=0, stalled=0) for t in tag_order}

    active_rows = []   # 정상 진행 중
    trouble_rows = []  # panic / stall / failed
    durations = {}     # tag -> [완료 작업 소요시간(초), ...]
    all_durations = []

    for j in jobs:
        st = per_tag[j["tag"]]
        st["total"] += 1
        info = analyze_file(j["path"])
        key = (j["binary"], j["trace"])
        proc = running.get(key)  # (pid, etimes) or None

        if info["complete"]:
            st["done"] += 1
            if info["dur"]:
                durations.setdefault(j["tag"], []).append(info["dur"])
                all_durations.append(info["dur"])
            continue

        if not info["exists"] and proc is None:
            st["pending"] += 1
            if show_all:
                active_rows.append((j, "PENDING", 0.0, 0, None, None))
            continue

        # 파일 존재(미완료) 또는 프로세스 존재
        last_instr = info["last_instr"]
        last_simsec = info["last_simsec"]
        etimes = proc[1] if proc else None
        pid = proc[0] if proc else None

        # 경과시간: 살아있는 프로세스면 실제 etimes, 아니면 마지막 heartbeat 시각
        elapsed = etimes if etimes is not None else last_simsec

        # 파일이 마지막으로 기록된 뒤 흐른 시간(= 진전이 멈춘 시간).
        # heartbeat 간격은 IPC가 낮으면 30분을 넘을 수 있으므로 mtime 기준이 가장 견고하다.
        frozen = (now_ts - info["mtime"]) if info["mtime"] else None

        # 멈춤 감지: 살아있는데 파일이 stall_min 분 이상 변화 없음
        stalled = (
            proc is not None
            and frozen is not None
            and frozen > stall_min * 60
        )

        frac = (last_instr / total_instr) if total_instr else 0.0
        # ETA 는 모든 상태(정상/패닉/멈춤)에서 동일하게 계산한다.
        eta = compute_eta(info["beats"], last_instr, elapsed, warmup, total_instr)

        if info["panic"]:
            st["panic"] += 1
            trouble_rows.append((j, "PANIC", frac, last_instr, elapsed, pid, frozen, eta))
            continue
        if proc is None:
            # 프로세스 없는데 미완료 → 중단/실패
            st["failed"] += 1
            trouble_rows.append((j, "FAILED", frac, last_instr, elapsed, pid, frozen, eta))
            continue
        if stalled:
            st["stalled"] += 1
            trouble_rows.append((j, "STALL", frac, last_instr, elapsed, pid, frozen, eta))
            continue

        # 정상 진행 중
        st["running"] += 1
        warm = last_instr < warmup
        active_rows.append((j, "RUN" + ("/wu" if warm else ""), frac,
                            last_instr, elapsed, eta))

    # ---------------- heartbeat 없는 작업(0M)의 ETA 폴백 ----------------
    # 자기 진행 데이터가 없으면 같은 실험의 완료 작업 소요시간 중앙값으로 추정한다.
    def _median(xs):
        if not xs:
            return None
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    def peer_eta(tag, elapsed):
        med = _median(durations.get(tag) or all_durations)
        if med is None:
            return None
        return max(0.0, med - (elapsed or 0))

    # peer 폴백은 '실제 진행 중인데 아직 heartbeat가 안 나온' 작업에만 적용한다.
    # 멈춤/실패 작업은 경과시간을 빼면 의미가 없으므로 ∞(추정 불가)로 둔다.
    def fill_active(r):
        j, state, frac, instr, elapsed, eta = r
        if eta is None and instr == 0 and state != "PENDING":
            eta = peer_eta(j["tag"], elapsed)
        return (j, state, frac, instr, elapsed, eta)

    active_rows = [fill_active(r) for r in active_rows]

    # ---------------- 출력 ----------------
    lines = []
    lines.append(BOLD(CYAN("ChampSim GAP 진행 모니터")) +
                 f"   {now}   " + GREY(f"(갱신 {interval}s, Ctrl-C 종료)"))
    lines.append(GREY(f"작업당 목표: {fmt_m(total_instr)} "
                      f"(warmup {fmt_m(warmup)} + sim {fmt_m(sim)})  "
                      f"활성 프로세스 {len(running)}개"))
    lines.append("=" * 92)

    g_total = sum(s["total"] for s in per_tag.values())
    g_done = sum(s["done"] for s in per_tag.values())
    g_run = sum(s["running"] for s in per_tag.values())
    g_pend = sum(s["pending"] for s in per_tag.values())
    g_panic = sum(s["panic"] for s in per_tag.values())
    g_fail = sum(s["failed"] for s in per_tag.values())
    g_stall = sum(s["stalled"] for s in per_tag.values())
    g_pct = (100.0 * g_done / g_total) if g_total else 0.0

    lines.append(
        BOLD("[전체]") + f"  완료 {GREEN(str(g_done))}/{g_total} ({g_pct:.1f}%)  "
        f"실행중 {CYAN(str(g_run))} · 대기 {g_pend} · "
        f"패닉 {RED(str(g_panic)) if g_panic else '0'} · "
        f"멈춤 {YELLOW(str(g_stall)) if g_stall else '0'} · "
        f"실패 {RED(str(g_fail)) if g_fail else '0'}"
    )
    lines.append("-" * 92)
    for t in tag_order:
        s = per_tag[t]
        pct = (100.0 * s["done"] / s["total"]) if s["total"] else 0.0
        extra = []
        if s["running"]:
            extra.append(CYAN(f"run {s['running']}"))
        if s["pending"]:
            extra.append(f"pend {s['pending']}")
        if s["panic"]:
            extra.append(RED(f"panic {s['panic']}"))
        if s["stalled"]:
            extra.append(YELLOW(f"stall {s['stalled']}"))
        if s["failed"]:
            extra.append(RED(f"fail {s['failed']}"))
        extra_s = ("  " + " · ".join(extra)) if extra else ""
        done_s = GREEN(f"{s['done']:>3}")
        lines.append(f"  {t:<34} {done_s}/{s['total']:<3} "
                     f"({pct:5.1f}%){extra_s}")

    # 진행 중 작업 표
    lines.append("")
    lines.append(BOLD("[진행 중인 작업]") +
                 GREY("  binary / trace / 진행률 / instr / 경과 / 예상남음"))
    lines.append(GREY("  (~ = 자기 진행속도 기준, ≈ = 동종 완료작업 중앙값 기준 추정)"))
    if not active_rows:
        lines.append(GREY("  (없음)"))
    else:
        active_rows.sort(key=lambda r: -r[2])  # 진행률 높은 순
        for j, state, frac, instr, elapsed, eta in active_rows:
            if state == "PENDING":
                lines.append(GREY(
                    f"  {j['binary']:<20} {j['trace']:<14} "
                    f"{'대기':<8}"))
                continue
            binary_s = CYAN(f"{j['binary']:<20}")
            pfx = "≈" if (instr == 0 and eta is not None) else "~"
            eta_s = GREEN(f"{pfx}{fmt_dur(eta)}")
            lines.append(
                f"  {binary_s} {j['trace']:<14} "
                f"{bar(frac)} {frac*100:5.1f}%  "
                f"{fmt_m(instr):>5}/{fmt_m(total_instr):<5} "
                f"{fmt_dur(elapsed):>6} → {eta_s}"
            )

    # 문제 작업
    if trouble_rows:
        lines.append("")
        lines.append(BOLD(RED("[주의: 패닉 / 멈춤 / 실패]")))
        order = {"PANIC": 0, "STALL": 1, "FAILED": 2}
        trouble_rows.sort(key=lambda r: order.get(r[1], 9))
        for j, state, frac, instr, elapsed, pid, frozen, eta in trouble_rows:
            tagcol = {"PANIC": RED, "STALL": YELLOW, "FAILED": RED}[state]
            if state == "STALL":
                tail_note = "평균속도 기준 추정" if eta is not None else "진행 0 — 추정불가"
                note = f"{fmt_dur(frozen)}째 기록 없음 — {tail_note}"
            else:
                note = {
                    "PANIC": "저IPC panic(IPC<0.01) — 기어가는 중, 사실상 안 끝남",
                    "FAILED": "프로세스 없음 — 중단/실패",
                }[state]
            pid_s = f"pid {pid}" if pid else "no-pid"
            state_s = tagcol(f"{state:<6}")
            eta_s = "∞" if eta is None else f"~{fmt_dur(eta)}"
            lines.append(
                f"  {state_s} {j['binary']:<20} {j['trace']:<14} "
                f"@ {fmt_m(instr):>5} ({frac*100:4.1f}%)  "
                f"경과 {fmt_dur(elapsed):>6} → 남음 {eta_s:>8}  "
                f"{pid_s:<11} {GREY(note)}"
            )

    return "\n".join(lines)


def clear_screen():
    sys.stdout.write("\033[2J\033[H")


def main():
    ap = argparse.ArgumentParser(description="GAP 벤치마크 실시간 진행 모니터")
    ap.add_argument("-i", "--interval", type=float, default=10.0,
                    help="갱신 간격(초), 기본 10")
    ap.add_argument("--once", action="store_true", help="한 번만 출력")
    ap.add_argument("--all", action="store_true",
                    help="완료/대기 작업까지 전부 표시")
    ap.add_argument("--stall-min", type=float, default=45.0,
                    help="이 분(min) 이상 출력파일 변화 없으면 STALL 판정, 기본 45 "
                         "(IPC가 낮으면 heartbeat 간격이 30분을 넘기도 하므로 넉넉히)")
    args = ap.parse_args()

    warmup, sim = parse_totals()
    total_instr = warmup + sim
    experiments = parse_experiments()
    traces = parse_active_traces()

    if not experiments:
        print(f"[오류] {RUNNER} 에서 실험을 찾지 못했습니다.", file=sys.stderr)
        sys.exit(1)
    if not traces:
        print(f"[오류] {RUN_GAP_COMMON} 에서 활성 트레이스를 찾지 못했습니다.",
              file=sys.stderr)
        sys.exit(1)

    jobs, bin2tag = build_jobs(experiments, traces)

    try:
        while True:
            out = render(jobs, bin2tag, total_instr, warmup, sim,
                         args.all, args.stall_min, args.interval)
            if args.once:
                print(out)
                break
            clear_screen()
            sys.stdout.write(out + "\n")
            sys.stdout.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        sys.stdout.write("\n중단됨.\n")


if __name__ == "__main__":
    main()
