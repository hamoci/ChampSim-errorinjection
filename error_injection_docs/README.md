# Error Injection Modeling v2 — Clustered (Poisson Cluster) Fault Model

DRAM error injection을 **시간 축(언제)과 공간 축(어디에)으로 분리**한 새 모델의 설계/구현/검증 문서.

## 문서 목록

| 문서 | 내용 |
|---|---|
| [01_problem_and_design.md](01_problem_and_design.md) | 기존 uniform 모델의 문제점과 새 설계의 핵심 아이디어 |
| [02_fault_modes.md](02_fault_modes.md) | Fault mode(cell/row/bank)의 정확한 의미와 field study 근거 |
| [03_code_walkthrough.md](03_code_walkthrough.md) | 코드 레벨 동작 흐름 (파일/함수 단위) |
| [04_config_reference.md](04_config_reference.md) | JSON 설정 키 레퍼런스 + 예시 |
| [05_verification.md](05_verification.md) | Smoke test 검증 절차와 결과 |
| [06_care_alignment_review_and_plan.md](06_care_alignment_review_and_plan.md) | CARE 구현 재검토(D1~D5)와 정렬 계획(P1~P7) |
| [07_care_design_analysis.md](07_care_design_analysis.md) | CARE 트리거(OR)·victim 정의·DDR5 지오메트리·용량 스케일링·면적 분석 |
| [08_intuition_and_faq.md](08_intuition_and_faq.md) | **직관 설명 + FAQ** — "CE 로그 생성기" 관점, reuse/앵커의 의미, 헷갈리기 쉬운 지점 교정 (다시 읽을 때 여기부터) |

## 30초 요약

기존(UNIFORM) 모델은 exponential 간격으로 에러 이벤트를 만들되, **에러 위치를 "그 순간
서비스되던 DRAM read의 주소"로 정했다.** DRAM address mapping이 bank를 골고루
interleave하므로 에러도 전 bank에 균등하게 흩어졌고, 같은 위치에서 에러가 반복되는
하드 fault 패턴이 없어 CARE의 proactive retirement(bank 편중 감지)가 절대 발화할 수
없었다.

새(CLUSTERED) 모델은 **Poisson cluster process**다:

1. **시간**: 에러 이벤트는 seed 지정 가능한 전용 RNG의 Poisson process로 발생
   (exponential inter-arrival, 평균 = `error_cycle_interval` CPU cycles).
   → 총 에러 개수의 기댓값은 설정한 확률 그대로 유지된다.
2. **공간**: 각 이벤트는 지속성 있는 **FaultDomain**(cell/row/bank 중 하나)의
   "재발현(manifestation)"이다. 확률 `fault_reuse_prob`로 기존 fault가 다시 발현되고,
   아니면 새 fault가 생성된다. 같은 fault의 에러는 같은 line/row/bank에만 떨어진다.
   → 실제 하드 fault처럼 에러가 공간적으로 뭉친다 (bank 편중, page당 다중 에러).
3. **재현성**: `error_seed` 하나로 시간/공간 RNG 스트림이 결정된다. 같은 seed → 같은
   에러 시퀀스. 기존 UNIFORM 모드는 바이트 단위로 동일하게 보존된다 (opt-in 방식).

## 빠른 사용법

```json
"error_page_manager": {
    "mode": "CYCLE",
    "error_cycle_interval": 144000,
    "error_spatial_model": "clustered",
    "error_seed": 54321
}
```

`error_spatial_model`을 생략하면(기본 `"uniform"`) 기존과 100% 동일하게 동작한다.
