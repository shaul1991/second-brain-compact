# Plan: 시맨틱 검색 v1 구현 계획

spec.md(R-001~R-010, A 안)을 어떻게 만들지를 정의한다. 구현은 이 plan 확정 후
`/goal @goal.md @spec.md @plan.md` 로 위임한다.

## 기술 접근 개요
second-brain-compact 는 이미 docker-compose 기반이고, 검색은 `services/retrieval/documents.py`
의 `search()` 단일 함수에 모여 있다. supermemory 도 Docker self-host 가 가능하므로:

1. supermemory(+ 오프라인 임베딩용 Ollama)를 docker-compose 서비스로 추가한다.
2. compact 코드의 `search()` 뒤에 supermemory 백엔드를 두고, 엔진이 없으면 기존 키워드
   검색으로 폴백한다. MCP 표면(recall/get_note/capture/status)은 그대로 둔다.
3. promote/archive 시점에 인덱스에 add/remove 하고, 볼트 전체 재구축용 reindex 명령을 둔다.

## Open questions 해소 (spec → 결정)
- **로컬 실행 형태** → Docker. docker-compose 에 `supermemory` 서비스와 `ollama` 서비스를
  추가하고, mcp/cli 서비스에 `SUPERMEMORY_BASE_URL=http://supermemory:6767`(내부 네트워크)
  을 주입. 임베딩은 Ollama 로컬 모델로 설정해 완전 오프라인. (정확한 self-host 환경변수 키·
  포트는 구현 전 upstream self-host README 로 확인 — 아래 검증 항목.)
- **점수 혼합/정렬** → supermemory `searchMode=hybrid` + `rerank` 결과 순서를 그대로 채택.
  supermemory similarity → 기존 hit 스키마의 `vector_score` 에 매핑, `keyword_score` 는 기존
  토크나이저 값 유지(투명성·폴백 공유). 엔진 다운 시 키워드 점수만으로 정렬.
- **인덱스 최신성** → promote 시 add / archive 시 remove + 수동 reindex. 파일 와처 없음(v1).
  Obsidian 등 직접 편집은 reindex 로 반영.
- **doc_id 매핑** → supermemory `customId` = 볼트 doc_id(`private:notes/<file>.md`). 검색 결과를
  볼트 노트로 1:1 역매핑. `containerTags` = 이 볼트 고정 태그 1개(예: 소유자 토큰). non-restricted
  만 색인하므로 restricted 누출 경로가 원천 차단(AC-2).

## 영향 모듈
- `services/retrieval/documents.py` — `search()` 에 semantic-first + keyword-fallback 분기.
- `services/retrieval/semantic.py` (신규) — supermemory SDK 얇은 래퍼: `add` / `remove` /
  `search` / `reindex` / `available()`. 모든 호출은 실패-안전(예외·타임아웃 → 폴백, 로그).
- `services/promotion/core.py` — `promote_capture` 끝에 add, `archive_capture` 끝에 remove 훅.
- `services/vault.py` — `load_config()` 에 supermemory 설정(base_url, container tag, enabled
  플래그, 임베딩 공급자) 추가.
- `bin/brain` — `reindex` 서브커맨드(R-003): 볼트 스캔(non-restricted) → 인덱스 재구축.
- `docker-compose.yml` — `supermemory`·`ollama` 서비스 추가, mcp/cli 에 base_url 주입.
- `.env.example` — `SUPERMEMORY_BASE_URL`, container tag, `SEMANTIC_SEARCH_ENABLED` 등 추가.
- `tests/` — AC-1~6 대응 테스트(엔진 모킹).

## 구현 단계
1. 설정 + `semantic.py` 래퍼(enabled 플래그 뒤, 비활성 시 동작 변화 0). `available()` 게이트.
2. promote/archive → add/remove 배선.
3. `search()` → semantic 우선 + 키워드 폴백.
4. `bin/brain reindex` 추가.
5. docker-compose 에 supermemory + ollama, env 배선.
6. AC-1~6 테스트.

## 데이터 흐름
```
promote → semantic.add(customId=doc_id, content, containerTags=[vault])  → 인덱스
recall  → semantic.search(q, hybrid, rerank) → doc_id 목록 → hit 스키마
          (엔진 unavailable → 기존 키워드 search 로 폴백)
archive → semantic.remove(customId=doc_id)
reindex → 볼트 non-restricted 스캔 → 인덱스 초기화 후 일괄 add
```

## 다중 로컬 클라이언트 / 동시성
로컬 Claude Code·Codex·Gemini 가 동시에 같은 볼트를 쓰는 것을 1급 시나리오로 본다
(goal 제약 "단일 플러그인", R-007).
- MCP 서버는 stdio 방식이라 클라이언트마다 자기 MCP 프로세스를 띄우되, 모두 같은 `data/`·
  `runtime/` 와 **하나의 공통 supermemory 서비스**를 공유한다. 인덱스를 프로세스에 박지 않고
  서비스로 뺀 선택이 다중 클라이언트 공유를 가능케 한다(HTTP API 가 동시 호출을 서버에서 처리).
- 검색·읽기(recall/get_note/status)는 다중 클라이언트 동시 실행에 안전하다.
- 동시 쓰기 주의: capture ID 채번 경합은 compact 의 기존 특성이며 이번 v1 범위 밖이다.
  `reindex` 는 다른 클라이언트가 promote/capture 중일 때 일시 불일치 가능 → 정비 작업으로
  한가할 때 실행한다(운영 주의).

## 리스크·완화
- **엔진 장애로 검색 불능** → `available()`/예외 처리로 항상 키워드 폴백(R-005). 엔진은 opt-in.
- **외부 송신 위험** → base_url 은 로컬 고정, 임베딩도 로컬 Ollama. 송신 0 을 테스트로 검증(AC-5).
- **restricted 누출** → 색인 입력을 `collect_documents(include_restricted=False)` 로 한정,
  promote 된 것만 add. restricted 는 어떤 경로로도 add 되지 않음(AC-2).
- **인덱스-정본 드리프트** → 인덱스는 runtime/(파생·재구축 가능). 의심 시 reindex.

## 구현 전 검증 항목 (사실 확인 필요)
- supermemory self-host Docker 이미지명·로컬 API 포트(6767 추정)·필수 환경변수.
- Ollama 를 임베딩 공급자로 지정하는 정확한 설정 키(self-host README).
- Python SDK 의 self-host base_url 지정 방식 및 add/search 시그니처.

## Traceability
- 단계 1·3·R-004/005/007/009 ↔ goal "검색 향상·단일 플러그인·폴백·감사".
- 단계 2·4·R-002/003/008 ↔ goal "파생 인덱스·기기 이전·재구축".
- 리스크 완화 ↔ goal "로컬 불변식·privacy 불변식".
