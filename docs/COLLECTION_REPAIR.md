# 수집 판정 및 경로 수정 — 로컬 검증 결과

2026-10-10, Skyblue.local. 최신 원격 기준 `fee434c`에서 수정했습니다. 원본 `/Users/air/codes/UN-news`는 `4b7744b`, tracked/untracked 변경 없음이 확인됐으며 그대로 보존했습니다. `/Users/air/Documents/international`은 commit 없는 빈 저장소였습니다. 수정 체크아웃은 `/Users/air/Documents/Codex/2026-10-10/task/international`입니다. 저장소와 상위 경로에서 적용되는 `AGENTS.md`, `.agents/skills`, `SKILL.md`는 발견되지 않았으며 README, HANDOFF, requirements 및 두 Actions 실행 지침을 읽었습니다.

## 수정 내용

- `src/monitor/sources.py`: list와 호환되는 `CollectionResult`에 후보, 성공, 실패, 필터 제외, max_items로 보류한 수를 기록합니다. 후보는 URL 중복 제거 후 계산하고, RSS/API는 입력 레코드를 기준으로 계산합니다. 후보 수는 키워드 관련성 분류 전 수입니다. 목록 요청 자체가 실패하면 후보/실패 수는 알 수 없으므로 null입니다.
- `error`: 전체 상세/레코드 실패, 요청/문서 오류, 목록 selector 불일치. `partial`: 수집 성공과 실패가 함께 있음. `empty`: 구조가 정상인 빈 RSS/API. `filtered`: 후보가 있었으나 소스 필터로 모두 제외됨. HTML에 후보가 없는 경우에는 실제 빈 목록임을 증명할 정보가 없으므로 구조 변경 오류로 보수적으로 판정합니다.
- RSS fallback은 유효한 RSS/Atom 구조인지 확인한 뒤 선택합니다. 유효한 fallback 성공은 정상이고 이전 endpoint 실패는 진단에 남깁니다. invalid feed/API records는 전체/부분 실패로 집계합니다.
- `src/main.py`: 소스 오류 후 나머지 수집을 계속하고, 결과 저장 후 전체/부분 오류가 있으면 exit 1을 반환합니다. partial 결과로 새 소스 기준선을 완료하지 않습니다.
- `config/sources.json`: BIS `/media-releases/` 허용, USTR `ul.listing li a[href]`, ILO 공식 뉴스룸 카드로 변경했습니다. 세 소스의 `collection_revision`을 추가해 첫 완전한 비어 있지 않은 수집 때 기준선을 갱신하고 알림을 억제합니다. partial/empty 결과로 revision을 완료하지 않습니다. dry-run은 revision이나 상태를 저장하지 않습니다.
- 기준선 갱신 중 기존 기사 내용이 달라져 `updated` event가 생겨도 알림을 보내지 않습니다. 기존 소스 기준선 migration은 한 번만 수행하며, 새 상태의 nested dict는 실행 간 공유되지 않습니다 (`src/monitor/state.py`).
- `src/healthcheck.py`: partial을 오류로 집계하고, 연속 0건 3회 및 마지막 정상 시각 18시간 초과/없음을 경고합니다. 마지막 정상 시각은 주간 창 바깥의 전체 로그도 읽어 계산합니다. 기존 `ok/collected=0` 로그는 정상 빈 응답의 증거로 취급하지 않습니다. 항목이 있는 partial 실행은 마지막 정상 시각을 갱신하지 않습니다. 비활성 소스는 제외합니다.
- `.github/workflows/monitor.yml`: monitor 단계의 성공/실패 후 정상 소스 상태와 실패 로그를 기존 commit 단계에 저장할 수 있도록 조건을 추가했습니다. monitor 단계의 실패는 job failure로 남습니다. 이 파일의 수정만 수행했으며 commit, push, 워크플로 실행은 하지 않았습니다.

## 공식 접근 경로 확인

일반 GET 요청으로 목록 및 소스별 상세 한 건만 확인했으며 운영 수집/발송을 실행하지 않았습니다.

| 소스 | 2026-10-10 로컬 읽기 결과 | 수정/제약 |
|---|---|---|
| BIS | 공식 RSS는 정상 XML, 최신 링크는 `/media-releases/` | 이전 필터가 제외하던 경로 추가 |
| USTR | 기존 selector 0건, 현재 `ul.listing` 29건; 상세 한 건 제목/본문 추출 | selector 교체 |
| ILO | 기존 `rss.xml`은 HTML; 공식 뉴스룸의 유효 카드 8건, 상세 한 건 제목/본문 추출 | 공식 HTML 목록으로 교체; 뉴스룸 카드 범위만 수집 |
| UN Press | 목록 11건, 상세 표본은 HTTP 406 | 기존 상세 수집을 error/partial로 정확히 기록; 상세 접근 제한은 남음 |
| UNCTAD | 목록 HTTP 403 challenge | 접근 제한은 남음; 우회하지 않음 |
| CISA | 이 머신의 목록 2건 및 상세 한 건은 정상 | 기존 공식 경로/selector는 유효함. Actions에서 발생한 403은 환경 차이로 남으며 일반 요청 실패는 오류로 기록 |

UN Press 목록이 직접 링크한 `https://press.un.org/en/rss.xml`은 정상 RSS 10건이었습니다. 보도자료, 회의보도, 브리핑, 블로그가 섞인 짧은 요약이며 category가 없었습니다. 기존 두 소스의 구분과 본문 기반 한국 관련 검색을 보장할 수 없어 자동 대체하지 않았습니다. 상세 접근 제한이 해소되거나 공식 범위별 본문 feed가 확인되기 전까지 제한이 남습니다.

참고 Actions 실행: https://github.com/coolpint/international/actions/runs/37983384367/job/113999213367 . 공개 페이지에서는 성공 판정과 로그 로그인 요구만 확인할 수 있었고, 원문 job 로그는 재다운로드하지 않았습니다. 진단은 제공된 상세 실패 근거와 저장소의 `data/run_logs`를 함께 사용했습니다.

`fee434c`의 마지막 로그까지 0건 또는 오류 연속 횟수: ILO 404회, CISA 333회, BIS 124회, UNCTAD 69회, USTR 68회, UN Press 5회. 오래된 `ok/0`가 포함되므로 원인별 실제 실패 횟수와 동일한 값은 아닙니다. 기존 로그는 수정하지 않았습니다.

## 검증

- 격리 환경 Python 3.12.13, beautifulsoup4 4.13.3.
- `.venv/bin/python -m unittest discover -s tests`: **55 tests passed**. 기존 29개 + 신규 26개. 전체/부분 상세 실패, valid empty RSS/Atom, HTTP 200 challenge, invalid XML/HTML/API schema, invalid records, selector mismatch, source filters/max_items, 현재 BIS/USTR/ILO fixture, 재기준선 알림 억제, zero streak 및 마지막 정상 시각, disabled source 제외를 검증합니다.
- 모든 활성 소스 설정과 실제 collectors를 쓰는 offline smoke dry-run (`tests/test_dry_run.py`): transport와 OAuth 응답은 mock, 실제 네트워크 접근은 금지, Telegram 호출 0회, 임시 경로 상태/이력/로그 쓰기 0회, 실패 소스 뒤 정상 소스 처리가 계속되고 exit 1 반환.
- non-dry-run 저장은 알림을 mock한 TemporaryDirectory에서만 테스트했습니다. 운영 `data/`는 변경되지 않았습니다.
- `.venv/bin/python -m compileall -q src tests`, `git diff --check` 통과. 두 Actions YAML의 syntax도 Ruby YAML parser로 확인했습니다.
- 깨끗한 최신 기준 clone에 제공 패치의 `git apply --check`/적용을 검증한 뒤 전체 테스트와 `data/` 무변경도 확인했습니다.
- World Bank 기존 테스트의 미래 날짜가 이미 지나 실패하므로 테스트 시계를 고정했습니다. 운영 날짜 필터 동작은 유지했습니다.

## 적용 방법과 범위

로컬 수정과 검증만 완료했습니다. 실제 서비스 복구 또는 Actions 환경의 접근 성공을 확인한 결과가 아닙니다. push, PR 게시, merge, 배포, 실제 워크플로 재실행, Telegram 발송 및 운영 데이터 변경은 수행하지 않았습니다.

별도 제공한 `international-collection-fix.patch`는 코드/설정/워크플로/문서/테스트만 포함합니다. 적용 승인을 받은 후 최신 main 기반의 깨끗한 작업 브랜치에서:

```sh
git apply --check /path/to/international-collection-fix.patch
git apply /path/to/international-collection-fix.patch
python -m unittest discover -s tests
```

현재 원본 체크아웃은 오래된 상태이므로 운영 기준선으로 쓰지 마세요. 승인된 적용 과정에서는 최신 main 및 운영 data를 보존해야 합니다. 실제 운영 반영은 이번 승인 범위 밖입니다. 최초 정상 실행은 세 수리 소스의 현재 기사 기준선을 저장하고 알림을 억제합니다. 그 다음 실행부터 신규/변경 항목 알림 대상이 됩니다. UN Press/UNCTAD 차단이 지속되면 정상 소스 처리는 계속되지만 job은 실패로 표시되는 것이 의도된 결과입니다.
