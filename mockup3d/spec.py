"""목업의 파라메트릭 형상 사양(MockupSpec).

AI가 도면/사진을 읽고 만들어내는 중간 표현이자, 사용자가 직접 수정할 수 있는 설계 데이터.
모든 길이 단위는 mm, 회전은 도(degree).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Primitive(BaseModel):
    """기본 도형 하나. 부품은 add 도형의 합집합에서 cut 도형을 뺀 결과다.

    치수 해석:
      box      : size_x × size_y × size_z
      cylinder : 지름 size_x, 높이 size_z (size_y 무시)
      cone     : 아래 지름 size_x, 위 지름 size_y, 높이 size_z
      sphere   : 지름 size_x (size_y, size_z 무시)
    위치(x, y, z)는 도형의 중심. 회전은 중심 기준 X→Y→Z 순서 오일러각.
    """

    label: str = Field(description="도형이 나타내는 형상 요소 (예: '바닥판', '나사 구멍')")
    shape: Literal["box", "cylinder", "cone", "sphere"]
    operation: Literal["add", "cut"]
    size_x: float
    size_y: float
    size_z: float
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rot_x: float = 0.0
    rot_y: float = 0.0
    rot_z: float = 0.0


class Part(BaseModel):
    """개별 출력 가능한 부품. 특허도면의 구성요소 하나에 대응시키는 것을 권장."""

    name: str
    ref_numeral: str = Field(default="", description="특허도면 부호 (예: '110'). 없으면 빈 문자열")
    primitives: list[Primitive]


class RefNumeral(BaseModel):
    """특허도면의 부호 ↔ 구성요소 대응. 부호는 치수가 아니다."""

    numeral: str
    name: str
    description: str = ""


class DimensionNote(BaseModel):
    """사양에 사용한 치수와 그 근거."""

    what: str
    value_mm: float
    source: Literal["drawing_dimension", "text", "user", "estimated"]


class MockupSpec(BaseModel):
    title: str
    source_type: Literal["photo", "patent_drawing", "sketch", "manual"]
    mode: Literal["appearance", "functional"] = Field(
        description="appearance=외형 확인용 목업, functional=조립/결합 검증용"
    )
    parts: list[Part]
    reference_numerals: list[RefNumeral] = Field(default_factory=list)
    dimensions: list[DimensionNote] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=list, description="도면/사진에 없어 추정한 내용 (뒷면, 내부, 치수 등)"
    )
    questions: list[str] = Field(
        default_factory=list, description="정확도를 높이기 위해 사용자에게 확인할 질문"
    )
