"""음성 입력 API. 받아 적은 문장을 규칙으로 갈라 저장소 메모의 품목이나 할 일로 넣는다.

음성 인식은 브라우저가 하고, 서버는 글만 받는다. 응답 형식은 docs/api.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import clock
from .memos import ITEMS_MAX_COUNT, ITEMS_TEXT_MAX_LENGTH, TITLE_MAX_LENGTH
from .store import Store
from .todos import MAX_LENGTH, Category

# 문장 끝에서 떼는 꼬리말: "추가", "추가해 줘", "추가해 주세요", "넣어 줘", "적어 줘", "담아 줘" 등.
# 앞에 붙는 "좀"도 함께 뗀다.
_TAIL = re.compile(
    r"(?:\s+좀)?\s*(?:추가(?:\s*(?:해|하기))?|넣어|적어|담아)(?:\s*(?:줘|주세요|줄래))?$"
)
# 메모 제목 뒤에 붙는 말
_PARTICLE = r"(?:에다가|에다|에는|에도|에)"
# 메모 제목 뒤에서는 음성 인식이 "에"를 잘못 받아 적은 것("의", "애", "예", "엔")도 함께 뗀다.
_TITLE_PARTICLE = r"(?:에다가|에다|에는|에도|에|의|애|예|엔)"
# "○○에 △△" 꼴. ○○이 메모 제목이 아니면 "제목 없음" 메모에 "○○ △△"로 넣는다.
_PLACE = re.compile(rf"^(\S.*?){_PARTICLE}\s+(\S.*)$")
UNTITLED = "제목 없음"
_COMMAS = re.compile(r"[,，、]")
_END_MARKS = ".!?。"


@dataclass
class Parsed:
    """문장을 가른 결과.

    kind: "memo"(제목 있는 메모의 품목), "untitled"("제목 없음" 메모의 품목), "todo"(일반 할 일)
    """

    kind: str
    memo_id: Optional[int] = None
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


def _match_title(sentence: str, name: str) -> Optional[tuple[str, bool]]:
    """문장이 이 메모 제목으로 시작하면 (나머지 글, "에"가 붙었는지)를 돌려준다. 띄어쓰기는 무시한다.

    "에"는 이름에 붙어 있어도("짐싸기에"), 떨어져 있어도("짐싸기 에") 뗀다.
    """
    chars = [re.escape(char) for char in name if not char.isspace()]
    if not chars:
        return None
    match = re.match(rf"{r'\s*'.join(chars)}\s*({_TITLE_PARTICLE})?(?:\s+|$)", sentence, re.IGNORECASE)
    if match is None:
        return None
    return sentence[match.end():], match.group(1) is not None


def parse(sentence: str, memos: list[dict]) -> Parsed:
    """받아 적은 문장을 가른다. memos는 제목 있는 메모 [{"id", "title"}].

    - 메모 제목으로 시작하면 그 메모의 품목. "에"나 꼬리말("추가해줘")이 없어도 된다
      (음성 인식이 "에"를 자주 빠뜨리거나 다르게 받아 적는다)
    - "○○에 △△ 추가해줘" 꼴인데 ○○이 메모 제목이 아니면 "제목 없음" 메모에 "○○ △△"
    - 그 밖에는 말한 그대로 일반 할 일
    """
    sentence = normalize(sentence)
    tail = _TAIL.search(sentence)
    body = sentence[: tail.start()].strip() if tail else sentence

    # 제목이 겹치면(예: "장"과 "장보기") 긴 제목을 먼저 본다.
    by_length = sorted(memos, key=lambda memo: len("".join(memo["title"].split())), reverse=True)
    for memo in by_length:
        matched = _match_title(body, memo["title"])
        if matched is None:
            continue
        rest, has_particle = matched
        items = split_spoken_items(rest)
        # 제목만 말한 것("장보기")은 품목이 없으니 넘어간다. "장보기에 추가해줘"는 품목이 없다고 알린다.
        if items or has_particle or tail:
            return Parsed("memo", memo_id=memo["id"], name=memo["title"], items=items)

    if tail:
        place = _PLACE.match(body)
        if place and len(place.group(1)) <= TITLE_MAX_LENGTH:
            name = place.group(1)
            # 어디에 넣으려던 것인지 남겨 두려고 말한 곳을 앞에 붙인다 ("약국 밴드").
            items = [f"{name} {item}" for item in split_spoken_items(place.group(2))]
            if items:
                return Parsed("untitled", name=name, items=items)
    return Parsed("todo", text=sentence)


class VoiceInput(BaseModel):
    text: str
    category: Category = "work"


router = APIRouter()


def _invalid(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


@router.post("/api/voice", status_code=201)
def add_by_voice(body: VoiceInput, request: Request) -> dict:
    store: Store = request.app.state.store
    if len(body.text) > ITEMS_TEXT_MAX_LENGTH:
        raise _invalid(f"한 번에 {ITEMS_TEXT_MAX_LENGTH}자까지 넣을 수 있습니다.")
    if not normalize(body.text):
        raise _invalid("아무 말도 듣지 못했습니다.")

    titled = [{"id": memo["id"], "title": memo["title"]} for memo in store.list_memos() if memo["title"]]
    parsed = parse(body.text, titled)
    text = normalize(body.text)

    if parsed.kind in ("memo", "untitled"):
        if not parsed.items:
            raise _invalid("넣을 품목을 듣지 못했습니다.")
        if len(parsed.items) > ITEMS_MAX_COUNT:
            raise _invalid(f"한 번에 {ITEMS_MAX_COUNT}개까지 넣을 수 있습니다.")
        if any(len(item) > MAX_LENGTH for item in parsed.items):
            raise _invalid(f"품목 하나는 {MAX_LENGTH}자까지 쓸 수 있습니다.")
        added = store.add_items_by_voice(parsed.memo_id, parsed.items, clock.now())
        if added is None:
            raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")
        memo = added["memo"]
        return {
            "result": parsed.kind,
            "name": memo["title"] or UNTITLED,
            "text": text,
            "memo": memo,
            "items": [item for item in memo["items"] if item["id"] in added["item_ids"]],
            "created_memo": added["created"],
            "todos": [],
        }

    if len(parsed.text) > MAX_LENGTH:
        raise _invalid(f"할 일은 {MAX_LENGTH}자까지 쓸 수 있습니다.")
    todo = store.add_todo(parsed.text, body.category)
    return {
        "result": "todo",
        "name": "",
        "text": parsed.text,
        "memo": None,
        "items": [],
        "created_memo": False,
        "todos": [todo],
    }
