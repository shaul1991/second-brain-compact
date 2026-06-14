# Spec: 시맨틱 검색 v1 (A — 정식 노트 의미 검색)

## Scope
v1 은 "정식 노트(promoted·non-restricted)를 의미 기반으로 검색"하는 것만 다룬다.
임시 메모(restricted capture)는 색인 대상이 아니며 비서에게 노출되지 않는다(= goal 의 A 안).
증류 제안 루프(B)는 다음 spec 으로 미룬다. A 안이라 A/B 칸막이 설계 자체가 이번엔 불필요하다.

## Requirements
- **R-001 (색인 대상)** — recall 이 이미 노출하는 문서 집합(non-restricted)만 로컬 인덱스에
  들어간다. restricted/draft capture·archive 는 절대 색인하지 않는다.
- **R-002 (색인 트리거)** — 노트가 promote 될 때 인덱스에 추가되고, archive 되면 제거된다.
- **R-003 (재색인)** — 볼트로부터 인덱스를 통째로 재구축하는 수동 명령(reindex)을 제공한다.
  새 기기·인덱스 손상·노트 직접 편집(Obsidian 등) 후 동기화 수단.
- **R-004 (검색 동작)** — recall 은 의미 기반(하이브리드) 검색 결과를 돌려준다. 비어 있던
  vector_score 가 실제 의미 점수로 채워진다. 결과는 기존과 동일한 형식의 hit 목록이며
  doc_id 로 볼트 노트에 매핑된다.
- **R-005 (폴백)** — 엔진이 없거나 응답하지 않으면 recall 은 기존 키워드 검색으로 자동
  폴백한다. supermemory 는 선택적(opt-in) 백엔드이고, 엔진 없이도 시스템은 동작한다.
- **R-006 (로컬·오프라인)** — 색인·검색의 모든 처리는 로컬에서 일어나며 외부로 데이터가
  나가지 않는다.
- **R-007 (인터페이스 불변)** — AI 도구가 보는 MCP 표면(recall/get_note/capture/status)은
  바뀌지 않는다. supermemory 는 recall 뒤에 숨고, 도구는 여전히 단일 플러그인 하나만 꽂는다.
- **R-008 (인덱스 위치)** — 인덱스는 runtime/ 아래(휘발·git ignore)에 둔다. 정본(data/
  Markdown)과 분리하며 백업/동기화 대상이 아니다(재구축 가능하므로).
- **R-009 (감사)** — recall 이 엔진을 호출하든 폴백하든 기존 감사 로깅을 유지한다.
- **R-010 (get_note 불변)** — get_note 는 기존대로 Markdown 정본을 직접 읽고 restricted 를
  반환하지 않는다. 의미 검색은 '찾기'만 바꾸고 '읽기'의 게이트는 그대로다.

## 확정된 설계 기본값 (검수 완료 2026-06-14)
- **색인 시점**: promote 시 추가 / archive 시 제거 + 수동 reindex. 실시간 자동 감지는 하지
  않는다(Simplicity First). Obsidian 등에서 직접 편집한 경우 reindex 로 맞춘다.
- **검색 방식**: supermemory 하이브리드(의미+키워드 내장)를 사용하고, 엔진이 꺼지면 기존
  키워드 검색으로 폴백한다.
- **restricted 처리**: v1 에서는 아예 색인하지 않는다(A 안이므로 칸막이 불필요).

## Acceptance criteria (인수 조건)
- AC-1: 키워드가 정확히 일치하지 않아도 의미가 통하는 질의로 정식 노트를 찾는다.
- AC-2: restricted capture 는 recall 결과에 절대 나오지 않으며 엔진으로도 전송되지 않는다.
- AC-3: 엔진을 끈 상태에서도 recall 이 키워드 폴백으로 동작한다.
- AC-4: 인덱스를 지우고 reindex 하면 볼트로부터 동등한 검색이 복구된다.
- AC-5: 색인·검색 중 외부 네트워크 송신이 0 이다.
- AC-6: get_note 는 변함없이 정본을 읽고 restricted 를 막는다.

## Out of scope
- 임시 메모(B) 색인 및 증류 제안 루프 → 다음 spec.
- Obsidian 적극 연동 → 별도 goal.
- supermemory 자동 기억 추출·모순·망각 활용 → B 이후.

## Open questions (plan 단계로)
- supermemory 로컬 실행 형태(컨테이너 vs 바이너리)와 docker-compose 편입 방식.
- 의미 점수와 키워드 점수의 혼합/정렬 규칙 세부.
- 노트 직접 편집 시 인덱스 최신성 정책(자동 감지 vs reindex 의존).
- supermemory 문서 id 와 볼트 doc_id(repo:path) 매핑 유지 방식.

## Traceability
모든 R-xxx 는 goal 의 Objective/Constraint 를 뒷받침한다.
