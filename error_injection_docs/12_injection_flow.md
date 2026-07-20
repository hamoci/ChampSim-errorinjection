# 12. Fault Injection 동작 흐름 (step-by-step 요약)

> sticky 모델의 주입 흐름을 4단계로 압축한 빠른 참조. 상세는 USER_MANUAL.md, 개념
> 직관은 08 문서. **핵심: 결함은 "태어날 때"와 "첫 read에 앵커될 때" 두 시점에 값을
> 나눠 얻고, 이후엔 자기 영역 read마다 CE를 계속 낸다.**

## 1단계 — 발생 (Poisson, 시간축)

랜덤한 사이클 간격(exponential inter-arrival, 평균 `error_cycle_interval`)으로 결함이
태어난다. 이때 **주사위로 정하는 것:**
- `mode` : CELL / ROW / BANK (FIT 가중치 18.6 : 8.2 : 10.0)
- `chip` : 0~7 (x8 die 중 어느 lane이 불량인가, 균등)
- `salt` : BANK 밀도 해시용 난수

**주소는 없다 (미앵커).** bank/row/line/channel/rank 아무것도 없음.
※ chip은 **주소와 무관** — "그 좌표가 8개 die 중 어느 die에서 불량인가"는 제조 우연이라 주사위로.

## 2단계 — 앵커 (첫 read, 공간축 확정)

Read가 오면, **미앵커 결함이 있으면 가장 오래된 것 하나를 그 read의 주소에 무조건 앵커**한다
(겹침 검사 없이 — 미앵커 결함은 다음 read를 그냥 가져감). 이때 read 주소에서 디코드해 저장:
- `bank_key` = **channel · rank · bankgroup · bank** 를 모두 인코딩한 유일 식별자
  (`(channel << 32) | (rank·BG·banks + BG·banks + bank)`)
- `row`, `anchor_cl`(line 주소)

→ 이제 결함은 **영구 Fault Address**(channel/rank 포함)를 가진다. 이후 절대 안 변함.
→ 결함 = { **태어날 때**: mode·chip·salt } + { **첫 read에서**: bank_key·row·line }.

## 3단계 — CE 발생 (이후 read마다, 지속)

앵커된 결함들을 **매 read마다 전부 검사**한다. **mode별 조건이 맞으면 CE**를 내고,
그 결함의 `chip`을 CE에 실어보낸다 (결함은 **소비/삭제되지 않고 계속 산다**):

| mode | CE 조건 | 밀집 방식 |
|---|---|---|
| **CELL** | `read.line == fault.anchor_cl` | 정확히 그 한 line |
| **ROW**  | `read.bank_key == fault.bank_key` ∧ `read.row == fault.row` | **다른 line이어도** 같은 (bank,row)면 CE |
| **BANK** | `read.bank_key == fault.bank_key` ∧ `is_bad_line(fault, line)` (밀도 5%) | **다른 주소여도** 같은 bank의 bad line이면 CE |

- **핵심(밀집):** "Read 주소가 달라도, 같은 결함 영역(ROW/BANK)이면 CE." 그래서 한 결함이
  자기 영역의 여러 주소에 CE를 뿌린다 = 공간 밀집.
- **주의:** `chip`은 **매칭 조건이 아니다** (read엔 chip이 없음). 결함에서 CE로 **실려 나갈** 뿐.
  → 한 결함의 CE는 (주소가 여럿이어도) 전부 같은 chip = lane 일관성 (CARE의 지문).

## 4단계 — 반복 + 생사 (lifecycle)

- Poisson이 계속 **새 결함을 낳고** (F0, F1, ... 공존), 매 read마다 전부 검사한다.
- page에 CE가 `retirement_threshold`만큼 쌓이면 **page 은퇴(migration)**:
  - **CELL/ROW 결함**: 그 page에 앵커됐으면 **죽음** (데이터가 건강한 프레임으로 이사).
  - **BANK 결함**: **생존** (bank 회로는 page 이사로 안 고쳐짐) → 그 bank의 다른 page에서 계속 CE.
  - 은퇴한 page는 **영구 차단** (살아남은 BANK 결함도 그 page엔 다시 CE 못 냄).

## 한 줄

> **타이머가 결함을 낳고(mode·chip·salt) → 첫 read가 주소를 박고(bank_key·row·line, ch/rank
> 포함) → 그 영역 read마다 CE(chip 실림, 결함은 계속 삶) → page 차면 은퇴(ROW/CELL 죽음,
> BANK 생존, 은퇴 page 영구 차단) → 반복.**

## 흔한 오해 교정
- ❌ "태어날 때 bank/row/line을 가진다" → ✅ 태어날 땐 mode·chip·salt뿐, 주소는 첫 read에서.
- ❌ "첫 접근도 영역 겹침을 검사한다" → ✅ 미앵커 결함은 무조건 다음 read에 앵커(검사 없음).
- ❌ "chip도 매칭 조건이다" → ✅ chip은 검사 대상 아님, 결함→CE로 실려 나감.
- ❌ "read를 소비하면 결함이 사라진다" → ✅ 결함은 안 사라짐, CE만 내고 계속 삶(은퇴만이 죽임).
- ✅ "다른 주소여도 같은 영역이면 CE" — 맞음, 이게 밀집의 원리.
