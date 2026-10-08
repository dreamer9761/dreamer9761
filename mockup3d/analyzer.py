"""Claude로 사진/특허도면을 읽어 MockupSpec을 만들고, 자연어 수정 요청을 반영한다."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import anthropic

from .spec import MockupSpec

MODEL = "claude-opus-5-5"

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

SYSTEM_PROMPT = """\
당신은 특허도면과 제품 사진을 3D 프린터용 목업 설계로 옮기는 기구설계 엔지니어입니다.
입력(사진, 특허도면, 명세서 발췌, 사용자 메모)을 읽고 MockupSpec을 작성합니다.

형상 표현
- 각 부품(part)은 기본 도형(box, cylinder, cone, sphere)의 add 합집합에서 cut 도형을 뺀 결과입니다.
- 좌표계: X=폭(좌우), Y=깊이(앞뒤), Z=높이(위). 단위 mm, 위치는 도형 중심, 회전은 도(degree).
- 출력 시 모델 전체가 바닥(z=0)에 놓이도록 자동으로 내려가므로 절대 높이는 신경 쓰지 않아도 됩니다.
- 구멍처럼 관통시킬 cut은 대상보다 1~2mm 길게 잡아 면이 겹치지 않게 합니다.
- 출력 가능한 범위로 단순화하되 식별 가능한 외형 특징(비율, 단차, 구멍, 홈)은 유지합니다.
- 벽 두께는 1.2mm 이상, 구멍 지름은 2mm 이상을 권장합니다.

특허도면 해석 규칙
- 도면의 숫자(100, 110, 120a 등)는 대부분 구성요소를 가리키는 '부호'이며 치수가 아닙니다.
  부호는 reference_numerals에 기록하고 해당 부품의 ref_numeral에 연결하세요. 절대 길이로 쓰지 마세요.
- 치수선·화살표·단위와 함께 표기된 값, 또는 명세서 본문에 명시된 수치만 실제 치수로 취급합니다.
- 실제 치수가 없으면 사진/도면의 비율과 일반적인 제품 크기로 추정하고, 그 사실을 dimensions(source=estimated)와
  assumptions에 남깁니다.
- 보이지 않는 뒷면·내부 구조는 추정임을 assumptions에 명시합니다.
- 사용자가 준 치수(user)가 있으면 가장 우선합니다.

정확도를 크게 바꿀 정보(전체 크기 기준값, 결합 방식, 내부 구조 등)가 없으면 questions에 구체적인 질문을 남기세요.
"""


def _content_block(path: Path) -> dict:
    media_type = mimetypes.guess_type(path.name)[0] or ""
    if media_type == "application/pdf":
        kind = "document"
    elif media_type in IMAGE_TYPES:
        kind = "image"
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {path.name} ({media_type or 'unknown'})")
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": kind, "source": {"type": "base64", "media_type": media_type, "data": data}}


class Analyzer:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL, effort: str = "high"):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def _parse(self, content: list[dict]) -> MockupSpec:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            # 안전 분류기가 거절하면 서버가 다른 모델로 재시도한다.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": content}],
            output_format=MockupSpec,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("모델이 요청을 거절했습니다.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("응답이 잘렸습니다. 도면을 나누거나 부품 수를 줄여 다시 시도하세요.")
        if response.parsed_output is None:
            raise RuntimeError("형상 사양을 해석하지 못했습니다.")
        return response.parsed_output

    def analyze(
        self,
        files: list[str | Path],
        notes: str = "",
        source_type: str = "auto",
        mode: str = "appearance",
    ) -> MockupSpec:
        """사진/도면 파일(이미지, PDF)과 메모로 새 사양을 만든다."""
        content: list[dict] = [_content_block(Path(f)) for f in files]
        request = [
            f"입력 종류: {source_type} (auto면 직접 판단)",
            f"목업 목적: {mode}",
        ]
        if notes.strip():
            request.append(f"사용자 메모/명세서 발췌/치수:\n{notes.strip()}")
        request.append("위 자료로 3D 프린터 출력용 MockupSpec을 작성하세요.")
        content.append({"type": "text", "text": "\n\n".join(request)})
        return self._parse(content)

    def refine(self, spec: MockupSpec, instruction: str, files: list[str | Path] = ()) -> MockupSpec:
        """기존 사양에 자연어 수정 요청을 반영한 새 사양을 만든다."""
        content: list[dict] = [_content_block(Path(f)) for f in files]
        content.append({
            "type": "text",
            "text": (
                "현재 MockupSpec(JSON):\n"
                f"{spec.model_dump_json(indent=1)}\n\n"
                f"수정 요청: {instruction}\n\n"
                "요청한 부분만 바꾸고 나머지는 유지한 전체 MockupSpec을 다시 작성하세요. "
                "사용자가 준 치수는 dimensions에 source=user로 기록하세요."
            ),
        })
        return self._parse(content)
