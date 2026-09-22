# international

여러 국가의 정부, 국제기구, 공공기관, 싱크탱크가 발표한 한국(대한민국,
북한, 한반도 전체)과 한국 기업 관련 공식 원문을 감지해 텔레그램 채널로
보내는 GitHub Actions 기반 모니터입니다. 한국 언론을 수집하거나 한국
언론 보도를 재인용한 항목을 다시 전달하는 용도로는 사용하지 않습니다.

다른 머신에서 이어받을 때 필요한 운영·환경 정보는
[docs/HANDOFF.md](docs/HANDOFF.md)에 정리되어 있습니다.

## Current Scope

- `UN News`
- `UN Press Releases`
- `UN Meetings Coverage`
- `UNRISD News`
- `UNRISD Publications`
- `WTO Latest News`
- `ILO Newsroom`
- `UK Foreign, Commonwealth & Development Office` (영어)
- `Global Affairs Canada` (영어)
- `Conseil de l’Union européenne` (프랑스어)
- `Auswärtiges Amt` (독일어)
- `中华人民共和国外交部发言人` (중국어)
- `The New York Times — Korea` (사용자 지정 고우선 미디어)
- `The Wall Street Journal — Korea` (사용자 지정 고우선 미디어)
- `ADB News`
- `World Bank News`
- `AIIB News`
- `BIS Press Releases`
- `ECB Press`
- `EIB Press Releases`
- `DOJ Press Releases`
- `U.S. Treasury Press Releases`
- `USTR Press Releases`
- `FBI National Press Releases`
- `CISA North Korea Cyber Advisories`
- `38 North`
- `SIPRI Publications`
- `CSIS Korea Chair`
- `RUSI Publications`

보류 중:

- `UNCTAD Publications`: 공식 페이지가 비브라우저 자동화에 반복적으로
  Cloudflare 403을 반환합니다.
- `Australia DFAT News`: 공식 목록은 확인했지만 live 파싱이 제한 시간
  안에 끝나지 않아 응답이 안정될 때까지 비활성화했습니다.
- `Crisis Group Korean Peninsula`: 공식 한반도 RSS는 확인됐지만 테스트한 자동화 환경에서 Cloudflare challenge가 발생했습니다.
- `Bruegel Publications`: 공식 publications 페이지는 확인됐지만 테스트한 자동화 환경에서 Cloudflare challenge가 발생했습니다.
- `CGD Publications`: 공식 feed는 확인됐지만 테스트한 자동화 환경에서 Cloudflare challenge가 발생했습니다.
- `PIIE Publications`: 공식 publications 페이지는 확인됐지만 테스트한 자동화 환경에서 Cloudflare challenge가 발생했습니다.
- `NK News`: 북한 전문 속보성 뉴스 소스로 한국 언론에서 이미 다루는 토픽과 중복되는 경우가 많아 비활성화했습니다.
- `Daily NK English`: 북한 전문 속보성 뉴스 소스로 한국 언론에서 이미 다루는 토픽과 중복되는 경우가 많아 비활성화했습니다.
- `VOA Korean Peninsula`: 한국어 한반도 뉴스 피드로 한국 언론에서 이미 다루는 토픽과 중복되는 경우가 많아 비활성화했습니다.
- `IEA News and Reports`: 공식 뉴스/보고서 페이지는 확인됐지만 테스트한 자동화 환경에서 비브라우저 요청에 Cloudflare challenge가 반환됐습니다.
- `UNDP`: 테스트한 자동화 환경에서 공식 사이트가 `Access Denied`를 반환했습니다.

## How It Works

1. GitHub Actions가 하루 3번 실행됩니다.
2. 최신 목록 페이지, RSS 피드, 또는 공식 JSON API를 읽고 후보 항목을 수집합니다.
3. HTML 소스는 상세 페이지를 다시 읽어 제목, 요약, 본문 일부를 추출합니다. RSS와 API 소스는 응답에 포함된 제목, 설명, 본문 조각을 바로 파싱합니다.
4. 영어·한국어뿐 아니라 프랑스어, 독일어, 스페인어, 포르투갈어,
   러시아어, 아랍어, 중국어, 일본어의 한국·북한·한반도 표현으로 1차
   판별합니다.
5. 한국 대기업, 금융, 방산, 조선, 배터리, 바이오, 플랫폼, 콘텐츠,
   게임, 항공 기업의 정식명과 주요 현지어 표기도 높은 관련도로
   판별합니다. `SK`, `LG`, `KT`, `Kia` 같은 모호한 단독 약어는
   사용하지 않습니다.
6. 한국 언론사명이 `according to`, `reported by`, `据…报道`,
   `…によると` 같은 인용 표현과 함께 나타나면 한국발 재인용 보도로
   보고 제외합니다. 한국 정부·공공기관의 공식 발표를 직접 인용한 해외
   원문은 제외하지 않습니다.
7. `38 North`, `CSIS Korea Chair`처럼 소스 자체가 한반도/북한
   전문이면서 정책·분석 성격이 강한 경우에는 소스 범위를 근거로 기본
   관련도를 부여합니다.
8. 뉴욕타임스와 월스트리트저널은 사용자가 지정한 예외입니다. Google
   News의 최근 30일 매체 제한 검색 RSS에서 발행처 이름과 도메인이
   해당 매체로 모두 확인된 결과를 `high`로 강제합니다. 다만 한국 언론
   재인용 제외가 최우선이므로 두 매체에도 같은 하드 게이트를 먼저
   적용합니다. 유료 본문을 직접 읽을 수 없는 운영 환경에서는 한국
   언론사별로 나눈 짧은 Google News 인용 검색 결과의 동일 기사 ID를
   제외합니다. 검색 요청이 실패하거나 결과가 있는데도 NYT·WSJ
   발행처로 검증되는 항목이 0건이면 검색 제약의 의미 변경으로 보고
   해당 소스 전체를 실패로 기록합니다.
9. 카카오/코코아 농작물 문맥처럼 알려진 오탐 패턴을 제외합니다.
10. `high` confidence 신규/업데이트 항목만 텔레그램 채널로 보냅니다.
    시크릿 미설정이나 일시 전송 실패로 현재 내용이 전달되지 않았으면
    성공할 때까지 다음 실행에서 재시도합니다.
11. `data/state.json`과 `data/history/*.ndjson`를 갱신하고 커밋합니다.
12. 각 모니터 실행 결과를 `data/run_logs/*.ndjson`에 저장해 주간
    건강점검에 활용합니다.

## Source Policy

- 해외 정부·국제기구·공공기관의 RSS, Atom, API, 공식 발표 페이지를
  우선합니다.
- 한국 언론사와 한국 언론의 해외판은 수집 소스로 추가하지 않습니다.
- 뉴욕타임스와 월스트리트저널만 사용자의 명시적 요청에 따른 고우선
  해외 미디어 예외이며, 다른 미디어에는 적용하지 않습니다.
- 새 소스는 실제 응답, 항목 추출, 상세 본문, URL 제한을 검증한 뒤
  활성화합니다.
- 응답 차단이나 반복적인 지연이 있는 소스는 오류를 누적시키지 않고
  보류 상태로 기록합니다.
- 세부 판단 기준은 [constitution.md](constitution.md), 변경 과정과
  검증 이력은 [plan.md](plan.md)를 따릅니다.

초기 실행은 `bootstrap` 모드입니다. 과거 글을 한꺼번에 알리지 않고, 현재 보이는 항목을 상태 파일에만 기록합니다.

새 소스를 나중에 추가한 경우에도 동일한 원칙을 적용합니다. 새 소스는 첫 성공 실행에서 현재 항목을 기준선으로만 저장하고, 그 다음 실행부터 신규/업데이트만 알립니다.

수동 테스트가 필요하면 GitHub Actions의 `Run workflow`에서 `mode=test_telegram`을 선택하면 텔레그램 테스트 메시지만 보냅니다.

## Telegram Secrets

GitHub repository에서 아래 경로로 들어가 시크릿을 추가하면 됩니다.

`Settings -> Secrets and variables -> Actions -> New repository secret`

필수 시크릿:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

추가 API 비용 없이 운영하는 구성이 기본값입니다.

- 알림 라벨과 설명은 한국어로 전송합니다.
- 기사 제목과 요약은 별도 번역 없이 원문 그대로 전송합니다.

`TELEGRAM_CHAT_ID`는 보통 아래 둘 중 하나입니다.

- 공개 채널 username: 예를 들어 `@my_channel`
- 채널 numeric id: 예를 들어 `-1001234567890`

봇은 채널의 관리자여야 합니다.

## Schedule

워크플로는 GitHub Actions 기준 UTC cron으로 설정되어 있습니다.

- `0 7,15,23 * * *`

이는 한국 시간(KST, UTC+9) 기준:

- `00:00`
- `08:00`
- `16:00`

주간 건강점검 워크플로도 함께 동작합니다.

- `45 6 * * 5`

이는 한국 시간 기준 매주 금요일 `15:45`입니다. 지난 7일간의 스케줄 실행, 소스 에러, 알림 전송 여부를 점검해 텔레그램으로 정상/이상 상태를 보냅니다.

## Layout

```text
.
├─ .github/workflows/monitor.yml
├─ .github/workflows/weekly-healthcheck.yml
├─ config/
│  ├─ keywords.json
│  └─ sources.json
├─ data/
│  ├─ history/
│  ├─ run_logs/
│  └─ state.json
├─ src/
│  ├─ healthcheck.py
│  ├─ main.py
│  └─ monitor/
└─ tests/
```

## Local Dry Run

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m src.main --dry-run
```
