# Handoff Guide

## Summary

이 프로젝트의 운영 런타임은 로컬 머신이 아니라 GitHub Actions입니다.

- 운영 기준으로는 `로컬 머신 의존성 없음`
- 개발과 수동 점검 기준으로는 `Python`, `git`, 네트워크, GitHub 인증이 필요`
- 텔레그램 알림과 GitHub Actions 설정은 GitHub repository 설정에 의존

즉, 다른 머신으로 옮겨도 저장소를 clone 하고 개발 도구만 맞추면 이어서 작업할 수 있습니다.

## What Is The Source Of Truth

이 프로젝트의 실제 운영 상태는 아래 세 곳에 있습니다.

1. GitHub repository
   - 코드
   - 설정
   - 상태 파일
   - 실행 이력
2. GitHub Actions
   - 스케줄 실행
   - 상태 파일 자동 커밋
3. GitHub Secrets
   - 텔레그램 봇 토큰
   - 텔레그램 채널 ID

## Runtime Dependencies

### Production Runtime

운영 시 필요한 것은 로컬 머신이 아니라 GitHub 쪽입니다.

| 항목 | 필요 여부 | 메모 |
|---|---|---|
| GitHub Actions | 필수 | 실제 스케줄 실행 주체 |
| Repository write 권한 | 필수 | `data/` 변경사항을 Actions가 commit/push 함 |
| GitHub Secrets | 필수 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| 외부 웹 접근 | 필수 | 공식 RSS/API/HTML 소스를 읽어야 함 |
| Telegram Bot | 필수 | 봇이 채널 관리자여야 함 |

### Local Development

다른 머신에서 코드 수정, 테스트, 수동 점검을 하려면 아래가 필요합니다.

| 항목 | 필요 여부 | 메모 |
|---|---|---|
| `git` | 필수 | clone, pull, push |
| Python | 필수 | GitHub Actions는 `3.12`, 로컬도 `3.12` 권장 |
| `venv` | 권장 | 로컬 격리 환경 |
| `pip` | 필수 | `requirements.txt` 설치 |
| 인터넷 연결 | 필수 | live dry-run, GitHub API, 외부 소스 검증 시 필요 |
| GitHub 인증 | 권장 | push, PR, 설정 변경 시 필요 |

### Python Dependencies

현재 `requirements.txt` 기준 런타임 Python 의존성은 매우 작습니다.

- `beautifulsoup4==4.13.3`

표준 라이브러리 의존성도 있습니다.

- `argparse`
- `json`
- `datetime`
- `pathlib`
- `urllib`
- `xml.etree.ElementTree`
- `zoneinfo`

## Confirmed Non-Dependencies

아래 항목들은 현재 운영에 필요하지 않습니다.

- 로컬 `cron`
- macOS `launchctl`
- 로컬 SQLite
- 로컬 비밀키 파일
- OpenAI API
- 하드코딩된 로컬 절대경로

즉, 이 저장소는 현재 `GitHub Actions + Git tracked state files` 구조이며, 특정 개인 Mac에 묶여 있지 않습니다.

## Repository-State Dependencies

운영 상태는 repository 안의 `data/` 디렉터리에 저장됩니다.

- [data/state.json](/Users/air/codes/UN-news/data/state.json)
- [data/history/](/Users/air/codes/UN-news/data/history)
- [data/run_logs/](/Users/air/codes/UN-news/data/run_logs)

중요한 점:

- 이 파일들이 실제 운영 기준선입니다.
- 새 머신에서 작업할 때는 반드시 최신 `main`을 pull 해야 합니다.
- 오래된 브랜치에서 작업하면 기준선이 뒤처져서 판단이 어긋날 수 있습니다.

## GitHub Configuration Dependencies

### Required Secrets

GitHub repository 설정에 아래 secret 이 있어야 운영 알림이 동작합니다.

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

설정 위치:

- `Settings -> Secrets and variables -> Actions`

### Telegram Requirements

- 봇은 대상 채널의 관리자여야 함
- `TELEGRAM_CHAT_ID`는 `@channel_username` 또는 `-100...` 형식 가능

### Workflow Files

- [monitor.yml](/Users/air/codes/UN-news/.github/workflows/monitor.yml)
- [weekly-healthcheck.yml](/Users/air/codes/UN-news/.github/workflows/weekly-healthcheck.yml)

운영상 중요한 GitHub 의존성:

- `monitor.yml`은 `contents: write` 권한이 필요
- 상태 커밋이 막히면 `data/`가 갱신되지 않음
- branch protection 이 Actions push 를 막으면 운영이 깨질 수 있음

## Local-Only Caveats

### 1. Weekly healthcheck repository fallback

[src/healthcheck.py](/Users/air/codes/UN-news/src/healthcheck.py) 에는 로컬 실행 시 기본 repository fallback 이 있습니다.

- 기본값: `coolpint/international`

같은 repository 를 다른 머신에서 이어받는 경우에는 문제 없습니다.

다만 아래 경우는 주의해야 합니다.

- 다른 repository 로 fork 해서 운영할 때
- repository 이름을 바꿨을 때

이 경우에는 로컬 healthcheck 실행 전에 `GITHUB_REPOSITORY` 환경변수를 명시하는 것이 안전합니다.

예:

```bash
export GITHUB_REPOSITORY=coolpint/international
python -m src.healthcheck --dry-run
```

### 2. Local dry-run vs real run

로컬에서 아래 명령은 상태 파일을 바꾸지 않습니다.

```bash
python -m src.main --dry-run
```

하지만 아래 명령은 로컬 `data/`를 실제로 바꿉니다.

```bash
python -m src.main
```

즉, 새 머신에서 실수로 non-dry-run 을 실행하면 로컬 작업트리에 상태 변경이 생길 수 있습니다.

### 3. Bootstrap behavior

새 소스를 추가한 직후 첫 성공 실행은 알림을 보내지 않고 기준선만 저장합니다.

이건 버그가 아니라 의도된 동작입니다.

## Move-To-New-Machine Checklist

### If You Are Continuing On The Same GitHub Repository

1. 저장소 clone
2. 최신 `main` checkout
3. Python 가상환경 생성
4. 의존성 설치
5. 테스트 실행
6. 필요하면 local dry-run
7. GitHub 인증 설정

권장 순서:

```bash
git clone git@github.com:coolpint/international.git
cd international
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests
python -m src.main --dry-run
```

### If You Are Moving To A New Repository Or Fork

위 단계에 더해서 아래를 반드시 확인해야 합니다.

1. GitHub Actions 활성화
2. `TELEGRAM_BOT_TOKEN` secret 복사
3. `TELEGRAM_CHAT_ID` secret 복사
4. Actions 가 branch 에 push 가능한지 확인
5. healthcheck 용 repository context 확인

## Operational Commands

### Local Test

```bash
python -m unittest discover -s tests
```

### Local Dry Run

```bash
python -m src.main --dry-run
```

### Local Telegram Test

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python -m src.main --test-telegram
```

### Local Weekly Health Check Dry Run

```bash
export GITHUB_TOKEN=...
export GITHUB_REPOSITORY=coolpint/international
python -m src.healthcheck --dry-run
```

## Known External Risks

이 프로젝트는 로컬 머신 의존성은 거의 없지만, 외부 사이트 의존성은 있습니다.

- 일부 기관은 Cloudflare challenge 로 막힘
- 일부 페이지는 HTML 구조가 바뀌면 selector 수정이 필요
- GitHub Actions 네트워크 환경에 따라 간헐 403/500 이 날 수 있음

현재 이런 이유로 `pending` 상태로 남겨둔 소스들이 있습니다.

## Conclusion

현재 구조는 `로컬 머신 종속형 프로젝트`가 아닙니다.

핵심 운영 의존성은 다음 세 가지입니다.

1. GitHub Actions
2. GitHub Secrets
3. repository 안의 `data/` 상태 파일

다른 머신에서 이어받을 때 필요한 것은 `개발 환경 재구성`과 `GitHub 접근 권한`이지, 기존 Mac 자체는 아닙니다.
