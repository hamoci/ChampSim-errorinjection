# 01. 기존 모델의 문제와 새 설계

## 1. 기존(UNIFORM) 모델의 동작

CYCLE 모드의 에러 주입은 두 단계로 동작했다.

1. **발생 (시간)** — `ErrorPageManager::update_cycle_errors()`가 매 DRAM 사이클마다
   호출되어, exponential 분포(평균 `error_cycle_interval` CPU cycles)로 샘플링한
   다음 발생 시각이 지나면 `pending_error_count`를 1 올린다.
   즉 **시간 축은 이미 Poisson process였다** (uniform 간격이 아님).
2. **부착 (공간)** — `DRAM_CHANNEL::service_packet()`에서 read packet을 서비스할 때
   `consume_cycle_error()`가 성공하면 **그 packet의 주소**에 에러를 기록한다.

## 2. 무엇이 문제였나

문제는 전부 2단계(공간)에 있다. 에러 위치 = "다음번 DRAM read가 우연히 향한 주소"이므로:

- **Bank 균등 분산**: DRAM address mapping은 성능을 위해 연속 주소를 channel/bank에
  의도적으로 interleave한다. 접근 스트림을 따라가는 에러도 자동으로 전 bank에 고르게
  퍼진다. 특정 bank에 에러가 집중되는 실제 하드 fault 패턴이 원천적으로 생길 수 없다.
- **지속성 없음**: 실제 DRAM fault는 물리적 결함이라 같은 위치에서 CE가 반복 발생한다.
  기존 모델은 매 에러가 독립 1회성이므로 "같은 page에 에러 N개 누적"(retirement
  threshold), "같은 line에서 CE 반복"(CARE의 S1→S2→S3 hard-error 확인) 같은 패턴이
  우연에만 의존한다.
- **CARE proactive가 검증 불가**: CARE(HPCA'21)의 proactive retirement는 ECC cache
  set별 8개 글로벌 카운터(bank id 기준)가 "saturation(=15) AND bias(max−min≥12)"일 때
  발화한다. 에러가 bank에 균등 분산되면 bias가 커질 수 없어 **증명 가능하게 절대 발화하지
  않는다** (`care_ecc_cache.h` 주석, full-scale probe 결과 AND 0/29).
- **재현성 취약**: seed가 54321로 하드코딩이고, 하나의 `std::mt19937`을 여러 용도가
  공유해서 설정으로 실험을 재현/변주할 수 없었다.

## 3. 새(CLUSTERED) 설계: Poisson Cluster Process

핵심 원칙: **"몇 개 발생하는가"와 "어디에 발생하는가"를 분리한다.**

```
시간 축  : Poisson process (전용 seeded RNG, 평균 간격 = error_cycle_interval)
              │  이벤트 발생 (총량은 설정한 확률을 따름)
              ▼
공간 축  : 각 이벤트 = FaultDomain의 manifestation(발현)
              ├─ 확률 fault_reuse_prob   : 기존 fault 중 하나가 재발현  ← 뭉침의 근원
              └─ 확률 1-fault_reuse_prob : 새 fault 생성 (mode ~ cell/row/bank 가중치)
              ▼
소비     : DRAM read가 fault 영역 안에 떨어질 때만 그 read에 에러 부착
              ├─ CELL: 같은 cache line     ├─ ROW: 같은 (bank, row)
              ├─ BANK: 같은 bank           └─ 미앵커 fault: 다음 read가 위치를 확정
```

### 설계 결정과 이유

1. **총량 보존** — 에러 개수는 여전히 시간 축 Poisson이 결정한다. 기존
   1e-5~1e-8 sweep(`error_cycle_interval` 환산)과 에러 개수 차원에서 그대로 비교 가능.
2. **Access-anchored fault** — 새 fault의 위치를 미리 정하지 않고, 다음에 소비하는
   read의 위치(bank, row, line)로 앵커한다. 이유: 위치를 무작위로 미리 정하면
   워크로드가 접근하지 않는 메모리에 fault가 떨어져 에러가 "보이지 않게" 되고,
   워크로드별로 유효 에러율이 달라져 비교가 무너진다. 앵커 방식은 모든 에러가 반드시
   실제 사용되는 데이터에 떨어진다는 기존 모델의 장점을 유지한다.
3. **기아(starvation) 단계적 확장** — 재발현 이벤트가 fault 영역과 일치하는 접근을
   만나지 못하면 매칭 영역을 단계적으로 넓힌다:
   `정확한 영역 → (error_starvation_cycles 경과) fault의 bank 전체 → (2× 경과) 아무 read나`.
   CELL fault의 anchor line은 LLC에 상주하는 동안 DRAM에서 재읽기되지 않으므로
   (특히 pinning이 그 line을 보호할 때) 기아가 구조적으로 흔하다 — smoke test에서
   전체 발현의 절반 이상. 첫 단계가 bank 확장이라 이 경우에도 에러가 fault의 bank
   안에 머물러 공간 뭉침이 보존되고, 마지막 단계가 총량을 보장한다. 각 단계 전환
   횟수는 통계로 기록된다.
4. **Opt-in + 기존 모드 보존** — `error_spatial_model: "clustered"`를 명시할 때만
   활성화. UNIFORM 모드는 RNG 스트림까지 기존과 동일해서 (전용 RNG는 CLUSTERED에서만
   사용) 기존 결과가 바이트 단위로 재현된다.
5. **RNG 이원화** — `temporal_rng`(발생 시각)와 `spatial_rng`(fault 샘플링)를 분리하고
   같은 `error_seed`에서 유도(`seed`, `seed ^ 0x9E3779B97F4A7C15`). 한쪽 소비 횟수가
   변해도 다른 쪽 스트림이 흔들리지 않는다.
6. **Retirement와 fault lifecycle (hard-fault 영속성)** — page retire = 데이터를 건강한
   frame으로 migration. 따라서 clustered 모드에서 retire는 영구적이다:
   `clustered_retired_pages`에 기록되어 그 PA에는 에러가 다시 기록되지 않는다
   (uniform의 "재등록→재-retire 루프" artifact 제거 — sticky fault에서는 이 루프가
   시스템적으로 발생하므로 필수). fault 자체는 물리 위치를 따른다:
   그 page에 앵커된 **CELL/ROW fault는 죽고** (옛 frame은 더 이상 읽히지 않음),
   **BANK fault는 생존한다** (bank 공유 회로는 page migration으로 안 고쳐짐 —
   CARE proactive의 전제). 죽은 fault 몫의 Poisson 이벤트는 살아있는 fault로
   **재샘플**되어 총 에러 개수는 계속 설정 확률을 따른다.

### 기대 효과

| 지표 | UNIFORM | CLUSTERED |
|---|---|---|
| 총 에러 수 | Poisson(rate) | Poisson(rate) — 동일 |
| page당 에러 수 | ~항상 1 (우연 제외) | fault 재발현으로 다중 에러 page 발생 |
| bank 분포 | 트래픽 비례 균등 | fault가 속한 bank로 편중 |
| CARE S1→S2→S3 | 같은 line 재에러가 거의 없어 S3 도달 희박 | CELL/ROW fault로 자연 발생 |
| CARE proactive | 발화 불가 | bank 편중으로 발화 가능 조건 형성 |
| retirement threshold | 도달 희박 | ROW/CELL 뭉침으로 현실적 도달 |
