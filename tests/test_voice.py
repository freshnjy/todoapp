"""음성 입력: 문장 가르기와 api/voice. 음성 인식 자체는 브라우저가 하므로 여기서는 글만 본다."""

import pytest

from backend.app.voice import parse, split_spoken_items

GROUPS = [
    {"id": 1, "name": "장보기", "category": "personal"},
    {"id": 2, "name": "여행 준비물", "category": "personal"},
    {"id": 3, "name": "장", "category": "personal"},
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
        # 음성 인식이 "에"를 빠뜨리거나 다르게 받아 적어도 묶음으로 들어간다
        ("장보기 우유", ["우유"]),
        ("장보기 에 우유 추가", ["우유"]),
        ("장보기의 우유 추가", ["우유"]),
        ("장보기애 우유 추가", ["우유"]),
        ("장보기 예 우유 추가해 줘", ["우유"]),
        ("장보기엔 우유", ["우유"]),
    ],
)
def test_sentence_goes_to_the_group(sentence, items):
    parsed = parse(sentence, GROUPS)
    assert (parsed.kind, parsed.group_id, parsed.items) == ("group", 1, items)


def test_group_name_with_a_space_matches_without_it():
    parsed = parse("여행준비물에 충전기 추가해줘", GROUPS)
    assert (parsed.kind, parsed.group_id, parsed.items) == ("group", 2, ["충전기"])


def test_longer_group_name_wins():
    assert parse("장보기에 두부 추가해줘", GROUPS).group_id == 1
    assert parse("장에 두부 추가해줘", GROUPS).group_id == 3


@pytest.mark.parametrize("sentence", ["치과 예약하기", "엄마께 전화, 은행 확인", "우유 추가해줘", "장보러 가기"])
def test_sentence_without_a_group_is_a_plain_todo(sentence):
    parsed = parse(sentence, GROUPS)
    assert (parsed.kind, parsed.text) == ("todo", sentence)


def test_group_name_at_the_start_is_enough():
    """ "에"도 꼬리말도 없어도 묶음 이름으로 시작하면 그 묶음에 넣는다."""
    groups = [{"id": 9, "name": "짐싸기", "category": "personal"}]
    for sentence in ("짐싸기 여권", "짐 싸기 여권 추가", "짐싸기의 여권 추가", "짐싸기에 여권 추가"):
        parsed = parse(sentence, groups)
        assert (parsed.kind, parsed.group_id, parsed.items) == ("group", 9, ["여권"]), sentence


def test_group_name_alone_is_a_plain_todo():
    assert parse("장보기", GROUPS).kind == "todo"
    # 이름이 다른 낱말의 앞부분일 뿐이면 묶음이 아니다
    assert parse("장보기용 가방 사기", GROUPS).kind == "todo"


@pytest.mark.parametrize(
    "sentence, name",
    [
        ("약국에 밴드 추가해줘", "약국"),
        ("회의록에 일정 추가해줘", "회의록"),
        ("내일 회의록에 일정 넣어 줘", "내일 회의록"),
    ],
)
def test_unknown_group(sentence, name):
    parsed = parse(sentence, GROUPS)
    assert (parsed.kind, parsed.name, parsed.text) == ("unknown_group", name, sentence)


def test_place_without_a_tail_is_a_plain_todo():
    assert parse("약국에 들르기", GROUPS).kind == "todo"


def test_no_groups_at_all():
    assert parse("장보기에 우유 추가해줘", []).kind == "unknown_group"
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

def add_group(client, name="장보기") -> dict:
    res = client.post("/api/groups", json={"name": name, "category": "personal"})
    assert res.status_code == 201
    return res.json()


def todos(client) -> list[dict]:
    return client.get("/api/todos").json()["todos"]


def test_voice_needs_login(client):
    assert client.post("/api/voice", json={"text": "장보기에 우유 추가해줘"}).status_code == 401


def test_voice_adds_an_item_to_the_group(logged_in):
    group = add_group(logged_in)
    res = logged_in.post("/api/voice", json={"text": "장보기에 우유 추가해줘"})
    assert res.status_code == 201
    data = res.json()
    assert data["result"] == "group"
    assert data["group"] == group
    assert [todo["text"] for todo in data["todos"]] == ["우유"]
    assert data["todos"][0]["group_id"] == group["id"]
    assert data["todos"][0]["category"] == "personal"
    assert todos(logged_in) == data["todos"]


def test_voice_adds_several_items(logged_in):
    group = add_group(logged_in)
    res = logged_in.post("/api/voice", json={"text": "장보기에 우유랑 계란하고 두부 추가해줘"})
    assert res.status_code == 201
    assert sorted(todo["text"] for todo in res.json()["todos"]) == ["계란", "두부", "우유"]
    assert all(todo["group_id"] == group["id"] for todo in todos(logged_in))


def test_voice_without_a_group_adds_a_plain_todo(logged_in):
    add_group(logged_in)
    res = logged_in.post("/api/voice", json={"text": "치과 예약하기", "category": "personal"})
    assert res.status_code == 201
    data = res.json()
    assert data["result"] == "todo"
    assert data["group"] is None
    assert data["todos"] == [
        {"id": data["todos"][0]["id"], "text": "치과 예약하기", "category": "personal", "done": False, "group_id": None}
    ]


def test_plain_todo_is_not_split(logged_in):
    res = logged_in.post("/api/voice", json={"text": "엄마랑 통화하고 은행 가기"})
    assert [todo["text"] for todo in res.json()["todos"]] == ["엄마랑 통화하고 은행 가기"]


def test_voice_category_defaults_to_work(logged_in):
    res = logged_in.post("/api/voice", json={"text": "보고서 쓰기"})
    assert res.json()["todos"][0]["category"] == "work"


def test_unknown_group_adds_nothing(logged_in):
    add_group(logged_in)
    res = logged_in.post("/api/voice", json={"text": "약국에 밴드 추가해줘"})
    assert res.status_code == 200
    data = res.json()
    assert (data["result"], data["name"], data["text"], data["todos"]) == (
        "unknown_group", "약국", "약국에 밴드 추가해줘", [],
    )
    assert todos(logged_in) == []
    assert [group["name"] for group in logged_in.get("/api/groups").json()["groups"]] == ["장보기"]


@pytest.mark.parametrize("text", ["", "   ", ". "])
def test_empty_sentence_is_rejected(logged_in, text):
    assert logged_in.post("/api/voice", json={"text": text}).status_code == 422


def test_group_without_an_item_is_rejected(logged_in):
    add_group(logged_in)
    res = logged_in.post("/api/voice", json={"text": "장보기에 추가해줘"})
    assert res.status_code == 422
    assert todos(logged_in) == []


def test_long_sentences_are_rejected(logged_in):
    add_group(logged_in)
    assert logged_in.post("/api/voice", json={"text": "가" * 101}).status_code == 422
    assert logged_in.post("/api/voice", json={"text": "장보기에 " + "가" * 101 + " 추가해줘"}).status_code == 422
    assert logged_in.post("/api/voice", json={"text": "가" * 1001}).status_code == 422
    assert todos(logged_in) == []


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
