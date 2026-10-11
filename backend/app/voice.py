"""음성 입력 API. 받아 적은 문장을 규칙으로 갈라 묶음의 품목이나 할 일로 넣는다.

음성 인식은 브라우저가 하고, 서버는 글만 받는다. 응답 형식은 docs/api.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .groups import ITEMS_MAX_COUNT, ITEMS_TEXT_MAX_LENGTH, NAME_MAX_LENGTH
from .store import Store
from .todos import MAX_LENGTH, Category

# 문장 끝에서 떼는 꼬리말: "추가", "추가해 줘", "추가해 주세요", "넣어 줘", "적어 줘", "담아 줘" 등.
# 앞에 붙는 "좀"도 함께 뗀다.
_TAIL = re.compile(
    r"(?:\s+좀)?\s*(?:추가(?:\s*(?:해|하기))?|넣어|적어|담아)(?:\s*(?:줘|주세요|줄래))?$"
)
# 묶음 이름 뒤에 붙는 말
_PARTICLE = r"(?:에다가|에다|에는|에도|에)"
# 묶음 이름 뒤에서는 음성 인식이 "에"를 잘못 받아 적은 것("의", "애", "예", "엔")도 함께 뗀다.
_GROUP_PARTICLE = r"(?:에다가|에다|에는|에도|에|의|애|예|엔)"
# "○○에 △△" 꼴. ○○이 묶음이 아닐 때 없는 묶음의 이름으로 본다.
_PLACE = re.compile(rf"^(\S.*?){_PARTICLE}\s+(\S.*)$")
_COMMAS = re.compile(r"[,，、]")
_END_MARKS = ".!?。"


@dataclass
class Parsed:
    """문장을 가른 결과.

    kind: "group"(묶음의 품목), "todo"(일반 할 일), "unknown_group"(없는 묶음)
    """

    kind: str
    group_id: Optional[int] = None
    items: list[str] = field(default_factory=list)
    text: str = ""
    name: str = ""


def normalize(sentence: str) -> str:
    """앞뒤 공백과 끝의 마침표를 떼고, 이어진 공백을 하나로 줄인다."""
    return " ".join(sentence.split()).rstrip(_END_MARKS).strip()


def _has_final_consonant(char: str) -> bool:
    """한글 글자에 받침이 있는지."""
    if not "가" <= char <= "힣":
        return False
    return (ord(char) - ord("가")) % 28 != 0


def _strip_object_particle(word: str) -> str:
    """끝의 "을/를"을 뗀다. 받침이 맞을 때만 뗀다 ("마늘을" → "마늘", "노을"은 그대로)."""
    if len(word) < 2:
        return word
    before, last = word[-2], word[-1]
    if last == "을" and _has_final_consonant(before):
        return word[:-1]
    if last == "를" and "가" <= before <= "힣" and not _has_final_consonant(before):
        return word[:-1]
    return word


def _joined_word(word: str) -> Optional[str]:
    """ "우유랑", "계란이랑", "계란하고"처럼 다음 품목으로 이어 주는 말이 붙었으면 뗀 낱말을 돌려준다."""
    if len(word) > 2 and word.endswith("하고"):
        return word[:-2]
    if len(word) > 2 and word.endswith("이랑") and _has_final_consonant(word[-3]):
        return word[:-2]
    if len(word) > 1 and word.endswith("랑") and "가" <= word[-2] <= "힣" and not _has_final_consonant(word[-2]):
        return word[:-1]
    return None


def split_spoken_items(text: str) -> list[str]:
    """말로 이어 붙인 품목을 나눈다. 쉼표와 "랑"·"하고"·"그리고"에서 나눈다."""
    items: list[str] = []
    for chunk in _COMMAS.split(text):
        words = chunk.split()
        current: list[str] = []
        for index, word in enumerate(words):
            is_last = index == len(words) - 1
            if word in ("그리고", "하고") and current and not is_last:
                items.append(" ".join(current))
                current = []
                continue
            joined = None if is_last else _joined_word(word)
            if joined:
                current.append(joined)
                items.append(" ".join(current))
                current = []
            else:
                current.append(word)
        if current:
            items.append(" ".join(current))
    if items:
        items[-1] = _strip_object_particle(items[-1])
    return [item for item in items if item]


def _match_group(sentence: str, name: str) -> Optional[tuple[str, bool]]:
    """문장이 이 묶음 이름으로 시작하면 (나머지 글, "에"가 붙었는지)를 돌려준다. 띄어쓰기는 무시한다.

    "에"는 이름에 붙어 있어도("짐싸기에"), 떨어져 있어도("짐싸기 에") 뗀다.
    """
    chars = [re.escape(char) for char in name if not char.isspace()]
    if not chars:
        return None
    match = re.match(rf"{r'\s*'.join(chars)}\s*({_GROUP_PARTICLE})?(?:\s+|$)", sentence, re.IGNORECASE)
    if match is None:
        return None
    return sentence[match.end():], match.group(1) is not None


def parse(sentence: str, groups: list[dict]) -> Parsed:
    """받아 적은 문장을 가른다. groups는 [{"id", "name", ...}].

    - 이미 있는 묶음 이름으로 시작하면 그 묶음의 품목. "에"나 꼬리말("추가해줘")이 없어도 된다
      (음성 인식이 "에"를 자주 빠뜨리거나 다르게 받아 적는다)
    - "○○에 △△ 추가해줘" 꼴인데 ○○이 묶음이 아니면 없는 묶음
    - 그 밖에는 말한 그대로 일반 할 일
    """
    sentence = normalize(sentence)
    tail = _TAIL.search(sentence)
    body = sentence[: tail.start()].strip() if tail else sentence

    # 이름이 겹치면(예: "장"과 "장보기") 긴 이름을 먼저 본다.
    by_length = sorted(groups, key=lambda group: len("".join(group["name"].split())), reverse=True)
    for group in by_length:
        matched = _match_group(body, group["name"])
        if matched is None:
            continue
        rest, has_particle = matched
        items = split_spoken_items(rest)
        # 묶음 이름만 말한 것("짐싸기")은 품목이 없으니 넘어간다. "짐싸기에 추가해줘"는 품목이 없다고 알린다.
        if items or has_particle or tail:
            return Parsed("group", group_id=group["id"], name=group["name"], items=items)

    if tail:
        place = _PLACE.match(body)
        if place and len(place.group(1)) <= NAME_MAX_LENGTH:
            return Parsed("unknown_group", name=place.group(1), text=sentence)
    return Parsed("todo", text=sentence)


class VoiceInput(BaseModel):
    text: str
    category: Category = "work"


router = APIRouter()


def _invalid(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


@router.post("/api/voice", status_code=201)
def add_by_voice(body: VoiceInput, request: Request, response: Response) -> dict:
    store: Store = request.app.state.store
    if len(body.text) > ITEMS_TEXT_MAX_LENGTH:
        raise _invalid(f"한 번에 {ITEMS_TEXT_MAX_LENGTH}자까지 넣을 수 있습니다.")
    if not normalize(body.text):
        raise _invalid("아무 말도 듣지 못했습니다.")

    groups = store.list_groups()
    parsed = parse(body.text, groups)

    if parsed.kind == "unknown_group":
        # 아무것도 넣지 않는다. 묶음을 새로 만들지도 않는다.
        response.status_code = 200
        return {"result": "unknown_group", "name": parsed.name, "text": parsed.text, "group": None, "todos": []}

    if parsed.kind == "group":
        if not parsed.items:
            raise _invalid("넣을 품목을 듣지 못했습니다.")
        if len(parsed.items) > ITEMS_MAX_COUNT:
            raise _invalid(f"한 번에 {ITEMS_MAX_COUNT}개까지 넣을 수 있습니다.")
        if any(len(item) > MAX_LENGTH for item in parsed.items):
            raise _invalid(f"품목 하나는 {MAX_LENGTH}자까지 쓸 수 있습니다.")
        todos = store.add_items(parsed.group_id, parsed.items)
        if todos is None:
            raise HTTPException(status_code=404, detail="묶음을 찾을 수 없습니다.")
        group = next(group for group in groups if group["id"] == parsed.group_id)
        return {"result": "group", "name": group["name"], "text": normalize(body.text), "group": group, "todos": todos}

    if len(parsed.text) > MAX_LENGTH:
        raise _invalid(f"할 일은 {MAX_LENGTH}자까지 쓸 수 있습니다.")
    todo = store.add_todo(parsed.text, body.category)
    return {"result": "todo", "name": "", "text": parsed.text, "group": None, "todos": [todo]}
