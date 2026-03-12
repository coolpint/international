# international

UN 및 산하기구의 한국(대한민국, 북한, 한반도 전체) 관련 업데이트를 감지해 텔레그램 채널로 보내는 GitHub Actions 기반 모니터입니다.

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

보류 중:

- `UNDP`: 테스트한 자동화 환경에서 공식 사이트가 `Access Denied`를 반환했습니다.

## How It Works

1. GitHub Actions가 하루 3번 실행됩니다.
2. 최신 목록 페이지 또는 RSS 피드를 읽고 후보 항목을 수집합니다.
3. HTML 소스는 상세 페이지를 다시 읽어 제목, 요약, 본문 일부를 추출합니다. RSS 소스는 피드의 제목, 설명, 본문 조각을 바로 파싱합니다.
4. 한반도 관련 키워드로 1차 판별합니다.
5. `high` confidence 신규/업데이트 항목만 텔레그램 채널로 보냅니다.
6. `data/state.json`과 `data/history/*.ndjson`를 갱신하고 커밋합니다.

초기 실행은 `bootstrap` 모드입니다. 과거 글을 한꺼번에 알리지 않고, 현재 보이는 항목을 상태 파일에만 기록합니다.

수동 테스트가 필요하면 GitHub Actions의 `Run workflow`에서 `mode=test_telegram`을 선택하면 텔레그램 테스트 메시지만 보냅니다.

## Telegram Secrets

GitHub repository에서 아래 경로로 들어가 시크릿을 추가하면 됩니다.

`Settings -> Secrets and variables -> Actions -> New repository secret`

필수 시크릿:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

한국어 번역까지 자동으로 받으려면 추가 시크릿:

- `OPENAI_API_KEY`

선택 변수:

- `OPENAI_TRANSLATION_MODEL`

`OPENAI_API_KEY`가 없으면 알림 라벨은 한국어로 가지만, 제목과 요약은 원문으로 남습니다.

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

## Layout

```text
.
├─ .github/workflows/monitor.yml
├─ config/
│  ├─ keywords.json
│  └─ sources.json
├─ data/
│  ├─ history/
│  └─ state.json
├─ src/
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
