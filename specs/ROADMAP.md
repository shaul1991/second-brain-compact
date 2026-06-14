# Roadmap: compact × supermemory 시너지

이 문서는 second-brain-compact 와 supermemory 를 **서로의 강점을 최대한 시너지 내는
구조**로 결합하는 큰 그림과, 그중 **무엇이 실현됐고 / 무엇이 구조적으로 열려 있고 /
무엇이 남았는지**를 정직하게 기록한다.

## 한 줄 비전
**compact = 쓰기·정본·거버넌스(헌법), supermemory = 읽기·지능·증류(두뇌).**
둘을 잇는 막(membrane)은 promote 게이트 하나다. supermemory 의 산출물은 절대 정본에
직접 쓰지 않고, **항상 사람이 승격하는 제안으로만** 게이트를 통과한다.

## 깨지면 안 되는 불변식 (전 단계 공통)
1. **승격(도장)은 사람만.** supermemory 는 제안만, 결정은 사람.
2. **전부 로컬·오프라인.** 외부(클라우드) 전송 0.
3. **Markdown = 단일 정본, supermemory = 재구축 가능한 파생 인덱스.**
4. **AI 도구는 단일 MCP 플러그인 하나만 꽂는다.** supermemory 는 뒤에 숨는다.
5. **restricted 는 recall 로 절대 새지 않는다.**

## 강점 보존·활용 현황
| 출처 | 강점 | 상태 |
|---|---|---|
| compact | 사람-루프 거버넌스 | ✅ 보존 |
| compact | Markdown 정본·소유 | ✅ 보존 |
| compact | privacy 불변식 | ✅ 보존+강화(egress 가드) |
| compact | 단일 MCP 플러그인 | ✅ 보존 |
| compact | 의존성 0 단순성 | ✅ 보존(stdlib·opt-in) |
| supermemory | 의미(시맨틱) 검색 | ✅ 활용(Phase A) |
| supermemory | 메모리 추출·증류 | ⬜ Phase B |
| supermemory | 모순 탐지·자동 갱신 | ⬜ Phase B |
| supermemory | 관계 그래프 | ⬜ Phase D |
| supermemory | 멀티모달 수집 | ⬜ Phase C |

→ **"두 강점의 공존"은 달성. "supermemory 강점의 최대 활용"은 검색 한 칸까지.**

## 단계 (Phases)

### Phase 0 — 구조 + 시맨틱 검색 v1  ✅ 완료
- 산출: `specs/001-supermemory-recall/` (goal/spec/plan), 구현, 테스트(AC-1~5).
- 내용: `search()` 시맨틱 우선 + 키워드 폴백, promote→색인, reindex, egress 가드,
  opt-in 백엔드(기본 OFF).
- 의의: 가장 큰 약점(멍청한 검색)을 메우고, 나머지 단계를 얹을 골격을 완성.

### Phase A-live — 실제 엔진 라이브 검증  ⬜ 다음
- supermemory self-host 이미지·포트(6767 가정)·필수 환경변수 확인.
- Ollama 를 임베딩 공급자로 묶는 정확한 설정 키 확인(완전 오프라인).
- 단건 DELETE 가 customId 를 받는지 확인(아니어도 reindex 가 보정).
- 근거: `specs/001-supermemory-recall/plan.md` "구현 전 검증 항목".

### Phase B — 증류 제안 루프 (supermemory 의 진짜 무기)  ⬜
- 임시 메모(capture)까지 **로컬 격리 컨테이너**에 색인 → supermemory 가 클러스터·증류·
  모순 탐지 → 결과를 **새 capture(제안)** 로 게이트에 되돌림.
- 결정 필요: A/B 라우팅 기준(출처/태그/플래그/레인) — `spec.md` Open question.
- 전제: "로컬 엔진은 봐도 recall 엔 안 샌다"는 칸막이를 코드로 강제.

### Phase C — 멀티모달 수집  ⬜
- capture 가 URL·PDF·이미지를 받고, supermemory 가 추출한 내용을 제안으로 환원.

### Phase D — 관계 그래프 / Obsidian 시각화  ⬜
- supermemory 의 부모/자식 관계를 `[[wikilink]]`/`related` 로 제안 → Obsidian 그래프 시각화.
- 별도 goal (goal.md Non-goal 에서 분리 명시).

## 진행 원칙
- 각 단계는 SDD(goal→spec→plan→/goal)로 진행하고, **한 단계 dogfood 후 다음**으로.
  (Simplicity First / spec 과확장 방지.)
- 어느 단계도 위 "불변식"을 깨면 안 된다. 깨야 한다면 먼저 goal 을 고친다.
