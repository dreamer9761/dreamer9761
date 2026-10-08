# AI 목업 프린터 (mockup3d)

사진이나 특허도면을 넣으면 AI가 **치수를 조정할 수 있는 3D 형상 사양**을 만들고,
STL로 변환 → 출력 가능 여부 검사 → 슬라이싱 → 3D 프린터 전송까지 이어지는 MVP입니다.

```
사진/특허도면(PNG·JPG·PDF) + 메모
        │  Claude (비전 + 구조화 출력)
        ▼
MockupSpec (부품 / 기본도형 add·cut / 도면 부호 / 치수 근거 / 추정 / 질문)   ← 말로 수정, JSON 직접 수정
        │  manifold3d (CSG, 항상 닫힌 솔리드)
        ▼
model.stl + 부품별 STL ──▶ 출력 검사(크기·얇은 벽·작은 구멍·오버행·떨어진 조각·재료량)
        │  PrusaSlicer CLI
        ▼
G-code ──▶ OctoPrint / Moonraker(Klipper) 업로드 및 출력 시작
```

## 왜 메시 생성 AI가 아니라 "파라메트릭 사양"인가

- 특허도면의 숫자(100, 110…)는 **부호이지 치수가 아닙니다.** AI가 부호는 `reference_numerals`에,
  실제 치수는 근거(`도면 치수 / 명세서 / 사용자 / 추정`)와 함께 `dimensions`에 따로 기록합니다.
- 결과가 기본 도형의 조합이라 "폭 100mm로", "구멍 지름 8mm" 같은 수정이 정확히 반영되고,
  출력물은 항상 닫힌(manifold) 솔리드라 슬라이서에서 깨지지 않습니다.
- 보이지 않는 뒷면·내부는 `assumptions`에, 정확도를 좌우하는 빈 정보는 `questions`에 남겨
  사람이 확인할 지점을 분명히 합니다.

사진 한 장으로 캐릭터·유기적 곡면을 만드는 용도라면 이미지→3D 메시 API(Meshy 등)를 별도 경로로 붙이는 편이 낫습니다.
이 저장소는 **케이스·브래킷·거치대처럼 기하 형상 위주의 제품 목업**을 1차 범위로 합니다.

## 실행

```bash
pip install -e '.[dev]'
export ANTHROPIC_API_KEY=...        # 또는 `ant auth login`

mockup3d serve                       # http://127.0.0.1:8000
```

웹 화면: 업로드 → AI 분석 → 3D 미리보기(회전) → 말로 수정 / JSON 수정 → 출력 검사 → 프린터 전송.
이전 작업은 `/?job=<id>`로 다시 열 수 있습니다.

CLI:

```bash
mockup3d analyze 특허도면.pdf 사진.jpg --notes "전체 폭 120mm, 부호 110은 받침판" -o out/
mockup3d build examples/phone_stand.json -o out/     # AI 없이 사양 → STL
```

### 프린터 연동 (선택)

**권장 기종: QIDI Q2** — Klipper + Moonraker가 기본 탑재되어 있어 별도 개조 없이 바로 연결됩니다.

```bash
export MOCKUP3D_PRINTER=moonraker
export MOCKUP3D_PRINTER_URL=http://<프린터 IP>:7125   # 프린터 화면의 네트워크 정보에서 IP 확인
export MOCKUP3D_PRINTER_PROFILE=qidi_q2              # 출력 검사에 270×270×256mm 적용
curl $MOCKUP3D_PRINTER_URL/server/info                # 연결 확인
```

슬라이싱 설정은 반드시 Q2용 프로필을 사용하세요. 일반 프로필로 만든 G-code는 Q2의 시작 매크로·온도 설정과 맞지 않을 수 있습니다.

| 환경변수 | 예시 |
|---|---|
| `MOCKUP3D_PRINTER` | `octoprint` 또는 `moonraker` |
| `MOCKUP3D_PRINTER_URL` | `http://octopi.local` / `http://klipper.local:7125` |
| `MOCKUP3D_PRINTER_API_KEY` | OctoPrint API 키 (Moonraker는 설정한 경우만) |
| `MOCKUP3D_SLICER` | PrusaSlicer 실행 파일 경로 (PATH에 있으면 생략) |

프린터·필라멘트 설정은 PrusaSlicer에서 내보낸 `.ini`를 `POST /api/jobs/{id}/print`의 `config_ini`로 넘깁니다.
출력 검사에서 오류(error)가 있으면 전송하지 않습니다. 오버행이 많으면 자동으로 지지대를 켭니다.

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/jobs` | multipart: `files[]`, `notes`, `source_type`, `mode` → AI 분석 + STL |
| POST | `/api/jobs/manual` | 사양 JSON으로 바로 생성 (AI 미사용) |
| GET | `/api/jobs/{id}` | 최신 사양·검사 결과·파일 목록 |
| POST | `/api/jobs/{id}/refine` | `{"instruction": "폭 100mm로"}` 자연어 수정 (새 버전 저장) |
| PUT | `/api/jobs/{id}/spec` | 사양 JSON 직접 수정 |
| GET | `/api/jobs/{id}/files/{name}` | STL 다운로드 |
| POST | `/api/jobs/{id}/print` | 슬라이싱 후 프린터 전송 |
| GET | `/api/printer/status` | 출력 진행 상태 |

## 구조

| 파일 | 역할 |
|---|---|
| `mockup3d/spec.py` | MockupSpec 데이터 모델 (AI 출력 스키마 겸 편집 포맷) |
| `mockup3d/analyzer.py` | Claude 호출: 이미지·PDF → 사양, 자연어 수정 |
| `mockup3d/geometry.py` | CSG 모델링, 바닥 정렬, STL 내보내기 |
| `mockup3d/printability.py` | 출력 전 검사, 재료량 추정 (`PrinterProfile`로 베드 크기 등 조정) |
| `mockup3d/slicer.py` | PrusaSlicer CLI 래퍼 |
| `mockup3d/printers/` | OctoPrint, Moonraker 클라이언트 |
| `mockup3d/server.py`, `static/index.html` | FastAPI + three.js 뷰어 |

## 현재 한계와 다음 단계

- 형상은 박스·원기둥·원뿔·구의 합/차입니다. 필렛, 스윕, 자유곡면이 필요하면 CadQuery(STEP 출력) 백엔드를 추가하세요.
- 얇은 벽 검사는 도형 단위 근사입니다. cut으로 생긴 얇은 벽은 슬라이서 미리보기로 한 번 더 확인하세요.
- AI 사양의 정확도는 도면 품질과 치수 정보에 크게 좌우됩니다. 대표 샘플 5~10건으로
  형상 재현도 / 사람 수정 시간 / 실제 출력 성공률을 측정해 범위를 정하는 것을 권장합니다.
- Bambu Lab(LAN·개발자 모드 필요), Elegoo Centauri(SDCP 프로토콜) 등은 별도 연동 모듈이 필요합니다.
- QIDI Studio / OrcaSlicer CLI 슬라이싱은 실제 Q2 프로필로 검증한 뒤 추가할 예정입니다.

## 테스트

```bash
pytest -q
```
AI와 프린터는 가짜 객체로 대체해 네트워크 없이 실행됩니다.
