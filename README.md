# international

UN 계열 기관, 국제기구, 싱크탱크, 미국 정부 보도자료의 한국(대한민국, 북한, 한반도 전체) 관련 업데이트를 감지해 텔레그램 채널로 보내는 GitHub Actions 기반 모니터입니다.

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
- `DOJ Press Releases`
- `U.S. Treasury Press Releases`
- `USTR Press Releases`
- `Crisis Group Korean Peninsula`
- `SIPRI Publications`
- `Bruegel Publications`
- `RUSI Publications`

보류 중:

- `CGD Publications`: 공식 feed는 확인됐지만 테스트한 자동화 환경에서 Cloudflare challenge가 발생했습니다.
- `PIIE Publications`: 공식 publications 페이지는 확인됐지만 테스트한 자동화 환경에서 Cloudflare challenge가 발생했습니다.
- `CSIS Korea Chair`: 공식 페이지는 확인됐지만 테스트한 자동화 환경에서 Cloudflare challenge 페이지가 반환됐습니다.
- `UNDP`: 테스트한 자동화 환경에서 공식 사이트가 `Access Denied`를 반환했습니다.

## How It Works

1. GitHub Actions가 하루 3번 실행됩니다.
2. 최신 목록 페이지, RSS 피드, 또는 공식 JSON API를 읽고 후보 항목을 수집합니다.
3. HTML 소스는 상세 페이지를 다시 읽어 제목, 요약, 본문 일부를 추출합니다. RSS와 API 소스는 응답에 포함된 제목, 설명, 본문 조각을 바로 파싱합니다.
4. 한반도 관련 키워드로 1차 판별합니다.
5. `high` confidence 신규/업데이트 항목만 텔레그램 채널로 보냅니다.
6. `data/state.json`과 `data/history/*.ndjson`를 갱신하고 커밋합니다.
7. 각 모니터 실행 결과를 `data/run_logs/*.ndjson`에 저장해 주간 건강점검에 활용합니다.

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
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m src.main --dry-run
```
