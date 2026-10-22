"""음성 입력: 문장 가르기와 api/voice. 음성 인식 자체는 브라우저가 하므로 여기서는 글만 본다."""

import pytest

from backend.app.voice import parse, split_spoken_items

# 제목 있는 메모
MEMOS = [
    {"id": 1, "title": "장보기"},
    {"id": 2, "title": "여행 준비물"},
    {"id": 3, "title": "장"},
]


# ---------- 문장 가르기 ----------

@pytest.mark.parametrize(
    "sentence, items",
    [
        ("장보기에 우유 추가해줘", ["우유"]),
        ("장보기에 우유 추가해 줘.", ["우유"]),
        ("장보기에 우유 추가", ["우유"]),
        ("장보기에 우유 넣어 줘", ["우유"]),
        ("장보기에 우유 좀 추가해 주세요", ["우유"]),
        ("장보기에 우유를 추가해줘", ["우유"]),
        ("장보기에 마늘을 추가해줘", ["마늘"]),
        ("장보기에다 우유 추가해줘", ["우유"]),
        ("장보기에 우유", ["우유"]),
        ("장보기 우유 추가해줘", ["우유"]),
        ("장 보기에 우유 추가해줘", ["우유"]),
        ("  장보기에   딸기 우유  추가해줘 ", ["딸기 우유"]),
        # 음성 인식이 "에"를 빠뜨리거나 다르게 받아 적어도 메모로 들어간다
        ("장보기 우유", ["우유"]),
        ("장보기 에 우유 추가", ["우유"]),
        ("장보기의 우유 추가", ["우유"]),
        ("장보기애 우유 추가", ["우유"]),
        ("장보기 예 우유 추가해 줘", ["우유"]),
        ("장보기엔 우유", ["우유"]),
    ],
)
def test_sentence_goes_to_the_memo(sentence, items):
    parsed = parse(sentence, MEMOS)
    assert (parsed.kind, parsed.memo_id, parsed.items) == ("memo", 1, items)


def test_memo_title_with_a_space_matches_without_it():
    parsed = parse("여행준비물에 충전기 추가해줘", MEMOS)
    assert (parsed.kind, parsed.memo_id, parsed.items) == ("memo", 2, ["충전기"])


def test_longer_memo_title_wins():
    assert parse("장보기에 두부 추가해줘", MEMOS).memo_id == 1
    assert parse("장에 두부 추가해줘", MEMOS).memo_id == 3


@pytest.mark.parametrize("sentence", ["치과 예약하기", "엄마께 전화, 은행 확인", "우유 추가해줘", "장보러 가기"])
def test_sentence_without_a_memo_title_is_a_plain_todo(sentence):
    parsed = parse(sentence, MEMOS)
    assert (parsed.kind, parsed.text) == ("todo", sentence)


def test_memo_title_at_the_start_is_enough():
    """ "에"도 꼬리말도 없어도 메모 제목으로 시작하면 그 메모에 넣는다."""
    memos = [{"id": 9, "title": "짐싸기"}]
    for sentence in ("짐싸기 여권", "짐 싸기 여권 추가", "짐싸기의 여권 추가", "짐싸기에 여권 추가"):
        parsed = parse(sentence, memos)
        assert (parsed.kind, parsed.memo_id, parsed.items) == ("memo", 9, ["여권"]), sentence


def test_memo_title_alone_is_a_plain_todo():
    assert parse("장보기", MEMOS).kind == "todo"
    # 제목이 다른 낱말의 앞부분일 뿐이면 그 메모가 아니다
    assert parse("장보기용 가방 사기", MEMOS).kind == "todo"


@pytest.mark.parametrize(
    "sentence, items",
    [
        ("약국에 밴드 추가해줘", ["약국 밴드"]),
        ("회의록에 일정 추가해줘", ["회의록 일정"]),
        ("내일 회의록에 일정 넣어 줘", ["내일 회의록 일정"]),
        ("약국에 밴드랑 소독약 추가해줘", ["약국 밴드", "약국 소독약"]),
    ],
)
def test_unknown_title_goes_to_untitled_with_the_place(sentence, items):
    parsed = parse(sentence, MEMOS)
    assert (parsed.kind, parsed.memo_id, parsed.items) == ("untitled", None, items)


def test_place_without_a_tail_is_a_plain_todo():
    assert parse("약국에 들르기", MEMOS).kind == "todo"


def test_no_memos_at_all():
    parsed = parse("장보기에 우유 추가해줘", [])
    assert (parsed.kind, parsed.items) == ("untitled", ["장보기 우유"])
    assert parse("치과 예약하기", []).kind == "todo"


@pytest.mark.parametrize(
    "text, items",
    [
        ("우유", ["우유"]),
        ("우유랑 계란하고 두부", ["우유", "계란", "두부"]),
        ("계란이랑 두부", ["계란", "두부"]),
        ("오이랑 당근", ["오이", "당근"]),
        ("우유 그리고 계란", ["우유", "계란"]),
        ("우유 하고 계란", ["우유", "계란"]),
        ("우유, 계란， 두부", ["우유", "계란", "두부"]),
        ("딸기 우유랑 식빵", ["딸기 우유", "식빵"]),
        ("우유랑 계란을", ["우유", "계란"]),
        ("포도", ["포도"]),
        ("노을", ["노을"]),
        ("사랑", ["사랑"]),
    ],
)
def test_split_spoken_items(text, items):
    assert split_spoken_items(text) == items


# ---------- API ----------

def add_memo(client, title="장보기", items=None) -> dict:
    res = client.post("/api/memos", json={"title": title, "items": items})
    assert res.status_code == 201
    return res.json()


def memos(client) -> list[dict]:
    return client.get("/api/memos").json()["memos"]


def todos(client) -> list[dict]:
    return client.get("/api/todos").json()["todos"]


def item_texts(memo) -> list[str]:
    return [item["text"] for item in memo["items"]]


def test_voice_needs_login(client):
    assert client.post("/api/voice", json={"text": "장보기에 우유 추가해줘"}).status_code == 401


def test_voice_adds_an_item_to_the_memo(logged_in):
    memo = add_memo(logged_in, items="계란")
    res = logged_in.post("/api/voice", json={"text": "장보기에 우유 추가해줘"})
    assert res.status_code == 201
    data = res.json()
    assert (data["result"], data["name"], data["created_memo"], data["todos"]) == ("memo", "장보기", False, [])
    assert data["memo"]["id"] == memo["id"]
    assert item_texts(data["memo"]) == ["계란", "우유"]  # 맨 아래에 붙는다
    assert [item["text"] for item in data["items"]] == ["우유"]  # 이번에 넣은 것만
    assert todos(logged_in) == []


def test_voice_adds_several_items(logged_in):
    add_memo(logged_in)
    res = logged_in.post("/api/voice", json={"text": "장보기에 우유랑 계란하고 두부 추가해줘"})
    assert res.status_code == 201
    assert [item["text"] for item in res.json()["items"]] == ["우유", "계란", "두부"]
    assert item_texts(memos(logged_in)[0]) == ["우유", "계란", "두부"]


def test_voice_skips_untitled_memos_when_matching_titles(logged_in):
    # 제목 없는 메모는 제목으로 고를 수 없다. "제목 없음"이라는 말도 제목이 아니다
    logged_in.post("/api/memos", json={"body": "그냥 메모"})
    res = logged_in.post("/api/voice", json={"text": "제목 없음에 우유 추가해줘"})
    assert res.json()["result"] == "untitled"


def test_unknown_title_creates_an_untitled_memo(logged_in):
    add_memo(logged_in)
    res = logged_in.post("/api/voice", json={"text": "약국에 밴드 추가해줘"})
    assert res.status_code == 201
    data = res.json()
    assert (data["result"], data["name"], data["created_memo"]) == ("untitled", "제목 없음", True)
    assert data["memo"]["title"] is None
    assert item_texts(data["memo"]) == ["약국 밴드"]
    assert [memo["title"] for memo in memos(logged_in)] == [None, "장보기"]
    assert todos(logged_in) == []


def test_unknown_title_uses_the_latest_untitled_memo(logged_in):
    older = logged_in.post("/api/memos", json={"body": "먼저 만든 것"}).json()
    newer = logged_in.post("/api/memos", json={"body": "나중에 만든 것"}).json()
    # 먼저 만든 것을 고쳐 가장 최근에 고친 메모로 만든다
    logged_in.patch(f"/api/memos/{older['id']}", json={"body": "고친 것"})
    data = logged_in.post("/api/voice", json={"text": "약국에 밴드 추가해줘"}).json()
    assert (data["memo"]["id"], data["created_memo"]) == (older["id"], False)
    assert item_texts(data["memo"]) == ["약국 밴드"]
    assert next(m for m in memos(logged_in) if m["id"] == newer["id"])["items"] == []


def test_voice_without_a_memo_title_adds_a_plain_todo(logged_in):
    add_memo(logged_in)
    res = logged_in.post("/api/voice", json={"text": "치과 예약하기", "category": "personal"})
    assert res.status_code == 201
    data = res.json()
    assert (data["result"], data["memo"], data["items"]) == ("todo", None, [])
    assert data["todos"] == [
        {"id": data["todos"][0]["id"], "text": "치과 예약하기", "category": "personal", "done": False, "memo_ids": []}
    ]


def test_plain_todo_is_not_split(logged_in):
    res = logged_in.post("/api/voice", json={"text": "엄마랑 통화하고 은행 가기"})
    assert [todo["text"] for todo in res.json()["todos"]] == ["엄마랑 통화하고 은행 가기"]


def test_voice_category_defaults_to_work(logged_in):
    res = logged_in.post("/api/voice", json={"text": "보고서 쓰기"})
    assert res.json()["todos"][0]["category"] == "work"


@pytest.mark.parametrize("text", ["", "   ", ". "])
def test_empty_sentence_is_rejected(logged_in, text):
    assert logged_in.post("/api/voice", json={"text": text}).status_code == 422


def test_memo_without_an_item_is_rejected(logged_in):
    add_memo(logged_in)
    res = logged_in.post("/api/voice", json={"text": "장보기에 추가해줘"})
    assert res.status_code == 422
    assert memos(logged_in)[0]["items"] == []


def test_long_sentences_are_rejected(logged_in):
    add_memo(logged_in)
    assert logged_in.post("/api/voice", json={"text": "가" * 101}).status_code == 422
    assert logged_in.post("/api/voice", json={"text": "장보기에 " + "가" * 101 + " 추가해줘"}).status_code == 422
    assert logged_in.post("/api/voice", json={"text": "약국에 " + "가" * 98 + " 추가해줘"}).status_code == 422
    assert logged_in.post("/api/voice", json={"text": "가" * 1001}).status_code == 422
    assert todos(logged_in) == []
    assert [memo["title"] for memo in memos(logged_in)] == ["장보기"]
    assert memos(logged_in)[0]["items"] == []


def test_bad_category_is_rejected(logged_in):
    assert logged_in.post("/api/voice", json={"text": "치과 예약하기", "category": "etc"}).status_code == 422


# ---------- 바로 듣기 주소 ----------

def test_voice_address_survives_the_login_redirect(client):
    res = client.get("/?voice=1", follow_redirects=False)
    assert (res.status_code, res.headers["location"]) == (303, "login.html?voice=1")
    res = client.get("/", follow_redirects=False)
    assert res.headers["location"] == "login.html"
    # 다른 값은 넘기지 않는다
    res = client.get("/?voice=1&next=//example.com", follow_redirects=False)
    assert res.headers["location"] == "login.html?voice=1"
