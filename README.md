# international

현재 Mac mini 개발·점검 폴더는 `/Users/sanghoon/codes/international`입니다.
정기 운영은 GitHub Actions이며 Index 볼륨에 의존하지 않습니다.

Slack 전환은 준비 단계입니다. 전용 웹훅 등록, 코드 운영 반영, 실제 전달 확인이
끝나기 전에는 운영 전환 완료가 아닙니다.

UN 계열 기관, 국제기구, 싱크탱크, 미국 정부 보도자료의 한국(대한민국, 북한, 한반도 전체) 관련 업데이트를 감지해 Slack 채널로 보내는 GitHub Actions 기반 모니터입니다.

다른 머신에서 이어받을 때 필요한 운영·환경 정보는 [docs/HANDOFF.md](docs/HANDOFF.md)에 정리되어 있습니다.

## Current Scope

- `UN News`
- `UN Press Releases`
- `UN Meetings Coverage`
- `UNCTAD Publications`
- `UNRISD News`
- `UNRISD Publications`
- `WTO Latest News`
- `ILO Newsroom`
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
4. 한반도 관련 키워드로 1차 판별합니다. `North Korean`, `South Korean` 같은 형용사형과 `북한`, `한국`, `한반도` 같은 한국어 키워드도 포함합니다.
5. `38 North`, `CISA North Korea Cyber Advisories`, `CSIS Korea Chair`처럼 소스 자체가 한반도/북한 전문이면서 정책·분석·공식 자료 성격이 강한 경우에는 소스 범위를 근거로 기본 관련도를 부여합니다.
6. 카카오/코코아 농작물 문맥처럼 알려진 오탐 패턴을 제외합니다. `Kakao Corp`, `KakaoBank`, `KakaoTalk` 같은 회사 문맥은 제외하지 않습니다.
7. `high` confidence 신규/업데이트 항목만 Slack 채널로 보냅니다.
8. `data/state.json`과 `data/history/*.ndjson`를 갱신하고 커밋합니다.
9. 각 모니터 실행 결과를 `data/run_logs/*.ndjson`에 저장해 주간 건강점검에 활용합니다.

초기 실행은 `bootstrap` 모드입니다. 과거 글을 한꺼번에 알리지 않고, 현재 보이는 항목을 상태 파일에만 기록합니다.

새 소스를 나중에 추가한 경우에도 동일한 원칙을 적용합니다. 새 소스는 첫 성공 실행에서 현재 항목을 기준선으로만 저장하고, 그 다음 실행부터 신규/업데이트만 알립니다.

수동 테스트가 필요하면 GitHub Actions의 `Run workflow`에서 `mode=test_slack`을 선택하면 Slack 테스트 메시지만 보냅니다.

## Slack Secrets

GitHub repository에서 아래 경로로 들어가 시크릿을 추가하면 됩니다.

`Settings -> Secrets and variables -> Actions -> New repository secret`

필수 시크릿:

- `SLACK_WEBHOOK_URL`: cooltaku의 [#international-news](https://cooltaku.slack.com/archives/C0CBMH52MEV)에 연결한 international 전용 Incoming Webhook URL

추가 API 비용 없이 운영하는 구성이 기본값입니다.

- 알림 라벨과 설명은 한국어로 전송합니다.
- 기사 제목과 요약은 별도 번역 없이 원문 그대로 전송합니다.

웹훅은 채널에 고정됩니다. Slack 앱의 Incoming Webhooks에서 목적지를
`#international-news`로 선택하고 전용 URL을 Actions 시크릿에 직접 등록합니다.
news-alert의 웹훅·자격정보는 사용하지 않습니다. URL을 채팅·문서·로그에 붙이지 않습니다.
[Slack 공식 설정 안내](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)

뉴스·장애·주간 점검은 Slack으로만 전송합니다. 웹훅 누락·실패 시 Telegram으로
폴백하지 않으며, 뉴스·장애 outbox는 다음 실행에서 재시도합니다. 주간 보고서
전송 실패는 workflow 실패로 처리하며 다음 예약 실행 또는 수동 재실행이 필요합니다.
전환 전 완료 hash는 과거 기사 재전송 방지 기준선으로 보존하고, 기존 대기 항목은
Slack으로 이어서 보냅니다. 새 성공 기록에는 `last_notified_channel=slack`을 남깁니다.
HTTP 성공 및 응답 본문 `ok` 확인 후 완료 처리합니다. 수락 직후 완료 저장 전에
프로세스가 종료되면 다음 시도에서 중복될 수 있습니다.

## Schedule

워크플로는 GitHub Actions 기준 UTC cron으로 설정되어 있습니다.

- `0 7,15,23 * * *`

이는 한국 시간(KST, UTC+9) 기준:

- `00:00`
- `08:00`
- `16:00`

주간 건강점검 워크플로도 함께 동작합니다.

- `45 6 * * 5`

이는 한국 시간 기준 매주 금요일 `15:45`입니다. 지난 7일간의 스케줄 실행, 소스 에러, 알림 전송 여부를 점검해 Slack으로 정상/이상 상태를 보냅니다.

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

## 수집 장애와 재전송

실행 로그의 `status`는 `success`, `partial_failure`, `total_failure`로 구분됩니다.
부분 장애는 Actions 경고 및 소스별 로그에 남기고 정상 소스 처리를 계속합니다.
전체 수집 실패 또는 Slack 미처리 대기열이 있으면 종료 코드 1을 반환합니다.
장애 알림은 동일 원인의 최초·변경·복구 때 전송하며, 실패한 자료/장애 알림은
`data/state.json`의 `notification_outbox`에 보관해 다음 실행에서 재시도합니다.

과거 오류 로그에 기록된 UN 원문 재수집은 Actions `mode=backfill` 또는
`python -m src.main --backfill`을 사용합니다. 기존 한국 관련성 판정과 URL
중복 제거를 적용합니다. 접근 불가로 발견하지 못한 전체 자료의 보충을 보장하지
않습니다. 공식 경로 검증 결과와 남은 UN·UNCTAD·CISA 제약은
[운영 수정 기록](docs/OPERATIONS_REPAIR.md)을 참조하세요.
