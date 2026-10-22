'use strict';

const MAX_LENGTH = 100;
// 메모 품목: 한 번에 넣는 글의 길이와 품목 수 (서버와 같은 값)
const ITEMS_TEXT_MAX_LENGTH = 1000;
const ITEMS_MAX_COUNT = 30;
const ADD_PLACEHOLDER = '할 일을 입력하세요';
// 입력 영역의 메모 버튼 수 (제목 있는 메모 중 최근에 고친 것)
const MEMO_CHIP_COUNT = 5;
const CATEGORY_LABELS = { work: '업무', personal: '개인', growth: '성장' };
const CATEGORY_VALUES = Object.keys(CATEGORY_LABELS);

// 자동 분류 키워드 (2글자 이상, 영어는 소문자)
const CATEGORY_KEYWORDS = {
  work: [
    '회의', '미팅', '회의록', '보고서', '메일', '기획', '제안서', '발표', '결재', '기안',
    '출근', '퇴근', '업무', '프로젝트', '거래처', '고객', '클라이언트', '계약', '견적',
    '회사', '팀장', '상사', '마감', '엑셀', '문서', '출장', '정산', '매출', '세금계산서', 'ppt',
  ],
  personal: [
    '장보기', '장보', '마트', '청소', '빨래', '설거지', '분리수거', '요리', '집안일',
    '병원', '치과', '약국', '은행', '운동', '헬스', '산책', '요가', '택배', '반납', '세탁',
    '미용실', '가족', '부모님', '엄마', '아빠', '친구', '약속', '생일', '선물', '여행', '관리비', '강아지',
  ],
  growth: [
    '공부', '독서', '책 읽기', '강의', '인강', '강좌', '영어', '일본어', '중국어', '단어',
    '자격증', '시험', '토익', '복습', '예습', '블로그', '글쓰기', '일기', '코딩', '알고리즘',
    '스터디', '세미나', '강연', '튜토리얼', '연습', '명상', '회고', '학원', '수업', '과제',
  ],
};

const WEEKDAY_LABELS = ['월', '화', '수', '목', '금', '토', '일']; // 0=월 ... 6=일 (서버와 같은 번호)
const RULE_TYPE_LABELS = { none: '반복 없음', daily: '매일', weekly: '요일 지정', monthly: '매월' };

const todayEl = document.getElementById('today');
const form = document.getElementById('add-form');
const input = document.getElementById('add-input');
const categorySelect = document.getElementById('add-category');
const addRuleEl = document.getElementById('add-rule');
const addOptionsEl = document.getElementById('add-options');
const addMoreEl = document.getElementById('add-more');
const listsEl = document.getElementById('lists');
const routineSectionEl = document.getElementById('routine-section');
const routineListEl = document.getElementById('routine-list');
const routineEmptyEl = document.getElementById('routine-empty');
const restEl = document.getElementById('rest');
const restSummaryEl = document.getElementById('rest-summary');
const restListEl = document.getElementById('rest-list');
const todoTitleEl = document.getElementById('todo-title');
const memoBarEl = document.getElementById('memo-bar');
const listEl = document.getElementById('todo-list');
const emptyEl = document.getElementById('empty');
const clearDoneBtn = document.getElementById('clear-done');
const tabsEl = document.getElementById('tabs');
const statusTabsEl = document.getElementById('status-tabs');
const progressBar = document.getElementById('progress-bar');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const statsEl = document.getElementById('stats');
const statsLabel = document.getElementById('stats-label');
const statsPercent = document.getElementById('stats-percent');
const noticeEl = document.getElementById('notice');
const logoutBtn = document.getElementById('logout');

const CONNECT_ERROR = '서버와 연결하지 못했어요. 잠시 후 다시 시도해 주세요.';

// 상태: 서버에서 받은 할 일, 루틴. 저장은 서버가 한다 (docs/api.md). 메모는 memos.js의 memos
// 할 일: { id, text, category, done }
let todos = [];
// 추가 폼에서 고른 메모의 id (없으면 할 일이나 루틴으로 들어간다). 등록한 뒤에도 그대로 둔다
let selectedMemo = null;
// 루틴: { id, text, category, rule, due(오늘 하는 날인지), done(오늘 했는지) }
let routines = [];
// 서버가 알려 준 오늘 (YYYY-MM-DD). 루틴을 체크할 때 이 날짜로 기록한다
let serverToday = null;
// 처음 불러오기가 끝났는지 (끝나기 전에는 "불러오는 중"을 보여 준다)
let loaded = false;
// 서버에 바꾸는 중인지 (끝날 때까지 다른 변경을 받지 않는다)
let busy = false;
// 화면 상태: 선택한 탭, 상태 필터 (저장하지 않음)
let currentFilter = 'all';
let statusFilter = 'all';
// 수정 중인 항목 { kind: 'todo' | 'routine', id, text, category, rule(루틴만) }
let editing = null;
// 사용자가 카테고리를 직접 고르면 이번 할 일은 자동 분류를 멈춘다
let categoryLocked = false;
// 추가 폼의 반복 설정 { type: 'none' | 'daily' | 'weekly' | 'monthly', days, day }
let addRule = createRuleState(null);

// 서버 호출. 주소는 상대 경로로 쓴다 (nginx가 /todo/ 접두사를 뗀다).
// 로그인이 풀렸으면(401) 로그인 화면으로 보낸다.
async function api(method, path, body) {
  const options = { method, credentials: 'same-origin' };
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (response.status === 401) {
    window.location.href = 'login.html';
    const error = new Error('로그인이 필요합니다.');
    error.unauthorized = true;
    throw error;
  }
  if (!response.ok) {
    const error = new Error(`서버 응답 ${response.status}`);
    error.status = response.status;
    // 서버가 알려 준 이유 (입력이 규칙에 맞지 않을 때의 문구). 없으면 비워 둔다
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') error.detail = data.detail;
    } catch (parseError) {
      // 본문이 JSON이 아니면 이유 없이 넘긴다
    }
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function showNotice(message) {
  noticeEl.textContent = message;
  noticeEl.hidden = false;
}

function clearNotice() {
  noticeEl.hidden = true;
  noticeEl.textContent = '';
}

function findItem(kind, id) {
  const list = kind === 'routine' ? routines : todos;
  return list.find((item) => item.id === id);
}

// 서버의 목록으로 화면을 다시 그린다 (날짜가 바뀌어 정리된 것, 다른 기기에서 바꾼 것 포함)
async function refresh() {
  // 메모는 입력 영역의 메모 버튼에도 쓰므로 어느 화면에서든 함께 받는다 (memos.js)
  const [todoData, routineData] = await Promise.all([
    api('GET', 'api/todos'),
    api('GET', 'api/routines'),
    fetchMemos(),
  ]);
  todos = todoData.todos.map((todo) => ({
    id: String(todo.id),
    text: todo.text,
    category: todo.category,
    done: todo.done,
  }));
  // 다른 기기에서 지우거나 제목을 뺀 메모는 고른 것에서도 뺀다
  const picked = selectedMemo === null ? null : findMemo(selectedMemo);
  if (!picked || !picked.title) selectedMemo = null;
  routines = routineData.routines.map((routine) => ({
    id: String(routine.id),
    text: routine.text,
    category: routine.category,
    rule: routine.rule,
    due: routine.due_today,
    done: routine.done_today,
  }));
  serverToday = routineData.today;
  // 습관 화면을 보고 있으면 그 기간의 기록도 함께 다시 받는다 (habits.js)
  if (currentView === 'habits') await fetchHabits();
  if (editing && !findItem(editing.kind, editing.id)) editing = null;
  loaded = true;
  render();
}

async function load() {
  try {
    await refresh();
    clearNotice();
  } catch (error) {
    if (!error.unauthorized) showNotice(CONNECT_ERROR);
  }
}

// 서버에 바꾼 뒤 목록을 다시 받는다. 성공하면 true.
// 실패하면 화면에 알리고, 화면을 서버에 저장된 상태(마지막으로 받은 목록)로 되돌린다.
async function change(request) {
  if (busy) {
    render();
    return false;
  }
  busy = true;
  try {
    await request();
    await refresh();
    clearNotice();
    return true;
  } catch (error) {
    if (!error.unauthorized) showNotice(CONNECT_ERROR);
    render();
    return false;
  } finally {
    busy = false;
  }
}

function normalizeCategory(category) {
  return CATEGORY_VALUES.includes(category) ? category : 'work';
}

// ---------- 반복 규칙 ----------

// 기기 시계 기준 오늘의 요일(0=월)과 날짜. 반복을 처음 고를 때의 기본값으로만 쓴다
function deviceWeekday() {
  return (new Date().getDay() + 6) % 7;
}

function deviceDayOfMonth() {
  return new Date().getDate();
}

// 서버의 규칙({type, days, day}) → 화면에서 고치는 상태. rule이 없으면 "반복 없음"
function createRuleState(rule) {
  return {
    type: rule ? rule.type : 'none',
    days: rule && rule.days ? [...rule.days] : [],
    day: rule && rule.day ? rule.day : deviceDayOfMonth(),
  };
}

// 화면 상태 → 서버에 보낼 규칙. { rule } 또는 { error }. "반복 없음"이면 { rule: null }
function ruleFromState(state) {
  if (state.type === 'none') return { rule: null };
  if (state.type === 'daily') return { rule: { type: 'daily' } };
  if (state.type === 'weekly') {
    if (state.days.length === 0) return { error: '반복할 요일을 하나 이상 골라 주세요.' };
    return { rule: { type: 'weekly', days: [...state.days].sort((a, b) => a - b) } };
  }
  const day = Number(state.day);
  if (!Number.isInteger(day) || day < 1 || day > 31) {
    return { error: '매월 며칠에 할지 1부터 31 사이로 넣어 주세요.' };
  }
  return { rule: { type: 'monthly', day } };
}

// 규칙을 한 줄 글로: "매일", "평일", "월·수·금", "매월 25일"
function ruleLabel(rule) {
  if (!rule) return '';
  if (rule.type === 'daily') return '매일';
  if (rule.type === 'monthly') return `매월 ${rule.day}일`;
  const days = [...rule.days].sort((a, b) => a - b);
  const key = days.join('');
  if (key === '0123456') return '매일';
  if (key === '01234') return '평일';
  if (key === '56') return '주말';
  return days.map((day) => WEEKDAY_LABELS[day]).join('·');
}

// 반복 설정 칸: 종류 선택 + (요일 지정이면) 요일 버튼 + (매월이면) 날짜.
// 넘겨받은 state를 직접 고친다. 다시 그려도 state가 남아 있어 값이 유지된다.
function createRuleControls(state, allowNone) {
  const wrap = document.createElement('div');
  wrap.className = 'rule-fields';

  const typeSelect = document.createElement('select');
  typeSelect.className = 'add-category rule-type';
  typeSelect.setAttribute('aria-label', '반복');
  Object.keys(RULE_TYPE_LABELS).forEach((value) => {
    if (value === 'none' && !allowNone) return;
    const option = document.createElement('option');
    option.value = value;
    option.textContent = RULE_TYPE_LABELS[value];
    typeSelect.append(option);
  });
  typeSelect.value = state.type;

  const daysBox = document.createElement('div');
  daysBox.className = 'rule-days';
  daysBox.setAttribute('role', 'group');
  daysBox.setAttribute('aria-label', '반복할 요일');
  const chips = WEEKDAY_LABELS.map((label, day) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'day-chip';
    chip.textContent = label;
    chip.setAttribute('aria-label', `${label}요일`);
    chip.addEventListener('click', () => {
      state.days = state.days.includes(day)
        ? state.days.filter((value) => value !== day)
        : [...state.days, day];
      sync();
    });
    daysBox.append(chip);
    return chip;
  });

  const monthBox = document.createElement('label');
  monthBox.className = 'rule-month';
  const dayInput = document.createElement('input');
  dayInput.type = 'number';
  dayInput.className = 'add-input rule-day';
  dayInput.min = '1';
  dayInput.max = '31';
  dayInput.inputMode = 'numeric';
  dayInput.value = String(state.day);
  dayInput.setAttribute('aria-label', '매월 며칠');
  dayInput.addEventListener('input', () => {
    state.day = dayInput.value === '' ? NaN : Number(dayInput.value);
  });
  const monthHint = document.createElement('span');
  monthHint.className = 'rule-hint';
  monthHint.textContent = '그 달에 없는 날짜면 마지막 날에 해요';
  monthBox.append('매월 ', dayInput, ' 일', monthHint);

  function sync() {
    daysBox.hidden = state.type !== 'weekly';
    monthBox.hidden = state.type !== 'monthly';
    chips.forEach((chip, day) => {
      const isOn = state.days.includes(day);
      chip.classList.toggle('is-on', isOn);
      chip.setAttribute('aria-pressed', String(isOn));
    });
  }

  typeSelect.addEventListener('change', () => {
    state.type = typeSelect.value;
    // 요일 지정을 처음 고르면 오늘 요일을 골라 둔다
    if (state.type === 'weekly' && state.days.length === 0) state.days = [deviceWeekday()];
    sync();
  });

  sync();
  wrap.append(typeSelect, daysBox, monthBox);
  return wrap;
}

function resetAddRule() {
  addRule = createRuleState(null);
  addRuleEl.replaceChildren(createRuleControls(addRule, true));
}

// ---------- 서버에 바꾸기 ----------

function addTodo(text, category) {
  return change(() => api('POST', 'api/todos', { text, category: normalizeCategory(category) }));
}

function addRoutine(text, category, rule) {
  return change(() => api('POST', 'api/routines', {
    text,
    category: normalizeCategory(category),
    rule,
  }));
}

function deleteTodo(id) {
  return change(() => api('DELETE', `api/todos/${id}`));
}

// 메모에 품목 넣기. 쉼표로 나누는 것은 서버가 한다
function addMemoItems(memoId, text) {
  return change(() => api('POST', `api/memos/${memoId}/items`, { text }));
}

// 쉼표로 나눈 품목 목록. 서버와 같은 규칙으로 미리 확인해 무엇이 틀렸는지 알려 준다.
// { items } 또는 { error }
function splitItems(text) {
  if (text.length > ITEMS_TEXT_MAX_LENGTH) {
    return { error: `한 번에 ${ITEMS_TEXT_MAX_LENGTH}자까지 넣을 수 있어요.` };
  }
  const items = text.split(/[,，、]/).map((piece) => piece.trim()).filter((piece) => piece !== '');
  if (items.length > ITEMS_MAX_COUNT) {
    return { error: `한 번에 ${ITEMS_MAX_COUNT}개까지 넣을 수 있어요.` };
  }
  if (items.some((piece) => piece.length > MAX_LENGTH)) {
    return { error: `품목 하나는 ${MAX_LENGTH}자까지 쓸 수 있어요.` };
  }
  return { items };
}

// 루틴 종료: 오늘부터 목록에 나오지 않는다. 지난 기록은 서버에 남는다
function endRoutine(id) {
  return change(() => api('POST', `api/routines/${id}/end`));
}

// 완료 전환. 할 일은 서버가 맨 끝으로 옮긴다. 루틴은 오늘 날짜의 기록을 적거나 지운다
function toggleItem(kind, id) {
  const item = findItem(kind, id);
  if (!item) return Promise.resolve(false);
  if (kind === 'routine') {
    const method = item.done ? 'DELETE' : 'PUT';
    return change(() => api(method, `api/routines/${id}/logs/${serverToday}`));
  }
  return change(() => api('PATCH', `api/todos/${id}`, { done: !item.done }));
}

// 완료 항목 일괄 삭제 (모든 카테고리의 할 일. 루틴과 메모는 지우지 않는다)
function clearDone() {
  return change(() => api('POST', 'api/todos/clear-done'));
}

// 수정 시작 (한 번에 한 항목만)
function startEdit(kind, id) {
  const item = findItem(kind, id);
  if (!item) return;
  editing = { kind, id, text: item.text, category: item.category };
  if (kind === 'routine') editing.rule = createRuleState(item.rule);
  render();
}

function cancelEdit() {
  editing = null;
  render();
}

// 빈 값이거나 저장에 실패하면 수정 상태를 유지한다
async function saveEdit() {
  if (!editing) return false;
  const { kind, id } = editing;
  const text = editing.text.trim().slice(0, MAX_LENGTH);
  if (text === '') return false;
  const body = { text, category: normalizeCategory(editing.category) };
  let path = `api/todos/${id}`;
  if (kind === 'routine') {
    const parsed = ruleFromState(editing.rule);
    if (parsed.error) {
      showNotice(parsed.error);
      return false;
    }
    body.rule = parsed.rule;
    path = `api/routines/${id}`;
  }
  const saved = await change(() => api('PATCH', path, body));
  if (!saved) return false;
  if (editing && editing.kind === kind && editing.id === id) editing = null;
  render();
  return true;
}

// ---------- 그리기 ----------

// 오늘 날짜 문구 (기기 현지 시간)
function formatToday() {
  const now = new Date();
  const days = ['일', '월', '화', '수', '목', '금', '토'];
  return `${now.getFullYear()}년 ${now.getMonth() + 1}월 ${now.getDate()}일 (${days[now.getDay()]})`;
}

function createButton(label, action, ariaLabel, extraClass = '') {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `btn btn-small ${extraClass}`.trim();
  button.dataset.action = action;
  button.textContent = label;
  button.setAttribute('aria-label', ariaLabel);
  return button;
}

// 한 줄: 체크박스 + 카테고리 배지 + 내용 + 버튼.
// 루틴은 내용 아래에 반복 규칙을 적고, 삭제 대신 종료 버튼을 둔다.
// checkable이 false면(오늘 해당 없는 루틴) 체크박스를 두지 않는다.
function createItem(kind, item, checkable = true) {
  const li = document.createElement('li');
  li.className = `todo-item cat-${normalizeCategory(item.category)}`;
  if (kind === 'routine') li.classList.add('is-routine');
  if (checkable && item.done) li.classList.add('is-done');
  if (!checkable) li.classList.add('is-rest');
  li.dataset.kind = kind;
  li.dataset.id = item.id;

  const check = document.createElement(checkable ? 'label' : 'span');
  check.className = 'todo-check';
  if (checkable) {
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = item.done;
    checkbox.dataset.action = 'toggle';
    checkbox.setAttribute('aria-label', `${item.text} 완료 표시`);
    check.append(checkbox);
  } else {
    check.setAttribute('aria-hidden', 'true');
  }

  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.textContent = CATEGORY_LABELS[normalizeCategory(item.category)];

  const text = document.createElement('span');
  text.className = 'todo-text';
  text.textContent = item.text;

  let main = text;
  if (kind === 'routine') {
    main = document.createElement('div');
    main.className = 'todo-main';
    const rule = document.createElement('span');
    rule.className = 'todo-rule';
    rule.textContent = ruleLabel(item.rule);
    main.append(text, rule);
  }

  const actions = document.createElement('div');
  actions.className = 'todo-actions';
  actions.append(
    createButton('수정', 'edit', `${item.text} 수정`),
    kind === 'routine'
      ? createButton('종료', 'end', `${item.text} 루틴 종료`, 'btn-danger')
      : createButton('삭제', 'delete', `${item.text} 삭제`, 'btn-danger'),
  );

  li.append(check, badge, main, actions);
  return li;
}

// 입력 영역의 버튼 줄: "할 일" + 제목 있는 최근 메모 몇 개. 지금 어디에 넣는지 눌린 모양으로 보인다.
// "할 일"은 할 일과 루틴을 넣는 기본 상태다. 메모 버튼이 하나도 없으면 고를 것이 없으니 보이지 않는다.
// 메모를 고르면 카테고리와 반복은 감춘다 (메모 품목에는 카테고리와 반복이 없다). 새 메모는 저장소 화면에서 만든다.
function renderMemoBar() {
  const titled = memos.filter((memo) => memo.title);
  const shown = titled.slice(0, MEMO_CHIP_COUNT);
  const picked = selectedMemo === null ? null : findMemo(selectedMemo);
  // 고른 메모가 최근 몇 개 밖으로 밀려났어도 버튼은 남긴다
  if (picked && !shown.includes(picked)) shown.push(picked);

  const plainChip = document.createElement('button');
  plainChip.type = 'button';
  plainChip.className = 'day-chip memo-chip';
  plainChip.classList.toggle('is-on', picked === null);
  plainChip.dataset.memo = 'none';
  plainChip.textContent = '할 일';
  plainChip.hidden = shown.length === 0;
  plainChip.setAttribute('aria-pressed', String(picked === null));
  plainChip.setAttribute('aria-label', '메모 없이 할 일이나 루틴으로 넣기');

  const chips = shown.map((memo) => {
    const isOn = memo === picked;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'day-chip memo-chip';
    chip.classList.toggle('is-on', isOn);
    chip.dataset.memo = String(memo.id);
    chip.textContent = memo.title;
    chip.setAttribute('aria-pressed', String(isOn));
    chip.setAttribute('aria-label', `${memo.title} 메모에 넣기`);
    return chip;
  });
  memoBarEl.replaceChildren(plainChip, ...chips);
  memoBarEl.hidden = shown.length === 0;

  addOptionsEl.hidden = Boolean(picked);
  input.placeholder = picked ? `${picked.title}에 넣을 것 (쉼표로 여러 개)` : ADD_PLACEHOLDER;
  input.maxLength = picked ? ITEMS_TEXT_MAX_LENGTH : MAX_LENGTH;
}

// 수정 중인 항목: 그 자리에 입력창 + (루틴이면 반복 설정) + 카테고리 + 저장/취소
function createEditItem(kind, item) {
  const li = document.createElement('li');
  li.className = `todo-item is-editing cat-${normalizeCategory(editing.category)}`;
  li.dataset.kind = kind;
  li.dataset.id = item.id;

  const editForm = document.createElement('form');
  editForm.className = 'edit-form';

  const editInput = document.createElement('input');
  editInput.type = 'text';
  editInput.className = 'add-input';
  editInput.maxLength = MAX_LENGTH;
  editInput.autocomplete = 'off';
  editInput.value = editing.text;
  editInput.dataset.action = 'edit-text';
  editInput.setAttribute('aria-label', kind === 'routine' ? '루틴 내용 수정' : '할 일 내용 수정');

  const editSelect = document.createElement('select');
  editSelect.className = 'add-category';
  editSelect.dataset.action = 'edit-category';
  editSelect.setAttribute('aria-label', '카테고리 수정');
  CATEGORY_VALUES.forEach((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = CATEGORY_LABELS[value];
    editSelect.append(option);
  });
  editSelect.value = normalizeCategory(editing.category);

  const saveBtn = document.createElement('button');
  saveBtn.type = 'submit';
  saveBtn.className = 'btn btn-primary';
  saveBtn.textContent = '저장';
  saveBtn.setAttribute('aria-label', '수정 내용 저장');

  const cancelBtn = createButton('취소', 'cancel', '수정 취소');

  const row = document.createElement('div');
  row.className = 'add-row';
  row.append(editSelect, saveBtn, cancelBtn);

  editForm.append(editInput);
  if (kind === 'routine') {
    const hint = document.createElement('p');
    hint.className = 'rule-hint';
    hint.textContent = '반복을 바꾸면 오늘부터 적용돼요. 지난 기록은 그대로 남아요.';
    editForm.append(createRuleControls(editing.rule, false), hint);
  }
  editForm.append(row);
  li.append(editForm);
  return li;
}

function isEditing(kind, item) {
  return editing !== null && editing.kind === kind && editing.id === item.id;
}

function createRow(kind, item, checkable = true) {
  return isEditing(kind, item) ? createEditItem(kind, item) : createItem(kind, item, checkable);
}

// 오늘 세는 항목: 오늘 하는 루틴 + 할 일 (탭 개수와 진행률에 쓴다). 메모 품목은 세지 않는다
function countedItems() {
  return [...routines.filter((routine) => routine.due), ...todos];
}

// 탭 버튼: 선택 표시와 카테고리별 개수
function renderTabs(counted) {
  tabsEl.querySelectorAll('.tab').forEach((tab) => {
    const filter = tab.dataset.filter;
    const isActive = filter === currentFilter;
    tab.classList.toggle('is-active', isActive);
    tab.setAttribute('aria-pressed', String(isActive));
    const count = filter === 'all'
      ? counted.length
      : counted.filter((item) => item.category === filter).length;
    tab.querySelector('.tab-count').textContent = count;
  });
}

// 상태 필터 버튼: 선택 표시
function renderStatusTabs() {
  statusTabsEl.querySelectorAll('.tab').forEach((tab) => {
    const isActive = tab.dataset.status === statusFilter;
    tab.classList.toggle('is-active', isActive);
    tab.setAttribute('aria-pressed', String(isActive));
  });
}

function getPercent(list) {
  if (list.length === 0) return 0;
  return Math.round((list.filter((item) => item.done).length / list.length) * 100);
}

// 통계 카드: 선택한 탭의 진행률 (상태 필터와 상관없이 카테고리 기준)
function renderStats(visible) {
  const total = visible.length;
  const doneCount = visible.filter((item) => item.done).length;
  const percent = getPercent(visible);

  statsEl.dataset.filter = currentFilter;
  statsLabel.textContent = currentFilter === 'all'
    ? '전체 진행률'
    : `${CATEGORY_LABELS[currentFilter]} 진행률`;
  statsPercent.textContent = `${percent}%`;
  progressFill.style.width = `${percent}%`;
  progressBar.setAttribute('aria-valuenow', String(percent));
  progressText.textContent = total === 0
    ? '아직 할 일이 없어요'
    : `${total}개 중 ${doneCount}개 완료`;
}

// 화면 전체 다시 그리기.
// 루틴: 만든 순서 그대로 (완료해도 자리를 옮기지 않는다). 할 일: 미완료 → 완료 순, 그 안은 서버 순서
function render() {
  todayEl.textContent = formatToday();

  const inCategory = (item) => currentFilter === 'all' || item.category === currentFilter;
  const inStatus = (item) => statusFilter === 'all' || (statusFilter === 'done') === item.done;

  // 루틴 구역: 루틴이 하나도 없으면 구역과 "할 일" 제목을 감춘다
  const dueRoutines = routines.filter((routine) => routine.due);
  const shownRoutines = dueRoutines.filter(inCategory).filter(inStatus);
  const restRoutines = routines.filter((routine) => !routine.due).filter(inCategory);
  routineSectionEl.hidden = routines.length === 0;
  todoTitleEl.hidden = routines.length === 0;
  routineListEl.replaceChildren(...shownRoutines.map((routine) => createRow('routine', routine)));
  routineEmptyEl.hidden = shownRoutines.length > 0;
  routineEmptyEl.textContent = dueRoutines.length === 0
    ? '오늘은 하는 날인 루틴이 없어요'
    : '해당하는 루틴이 없어요';
  restEl.hidden = restRoutines.length === 0;
  restSummaryEl.textContent = `오늘 해당 없는 루틴 ${restRoutines.length}개`;
  restListEl.replaceChildren(...restRoutines.map((routine) => createRow('routine', routine, false)));

  // 미완료 → 완료 순으로, 상태 필터에 맞는 것만
  const byStatus = (list) => [
    ...(statusFilter === 'done' ? [] : list.filter((todo) => !todo.done)),
    ...(statusFilter === 'active' ? [] : list.filter((todo) => todo.done)),
  ];

  renderMemoBar();

  // 할 일
  const visibleTodos = todos.filter(inCategory);
  const ordered = byStatus(visibleTodos);
  listEl.replaceChildren(...ordered.map((todo) => createRow('todo', todo)));
  // 빈 안내: 할 일 자체가 없을 때와 상태 필터로 걸러져 없을 때를 구분
  emptyEl.hidden = ordered.length > 0;
  if (!loaded) emptyEl.textContent = '불러오는 중이에요';
  else if (visibleTodos.length === 0) emptyEl.textContent = '오늘 할 일을 추가해 보세요';
  else emptyEl.textContent = '해당하는 할 일이 없어요';
  clearDoneBtn.hidden = !todos.some((todo) => todo.done);

  const counted = countedItems();
  renderTabs(counted);
  renderStatusTabs();
  renderStats(counted.filter(inCategory));
  renderHabits();
  renderMemos();
}

function itemSelector(kind, id) {
  return `[data-kind="${kind}"][data-id="${id}"]`;
}

// 다시 그린 뒤 같은 항목의 같은 컨트롤에 포커스를 되돌린다 (키보드 사용)
function restoreFocus(kind, id, action) {
  const target = listsEl.querySelector(`${itemSelector(kind, id)} [data-action="${action}"]`);
  if (target) target.focus();
}

// 수정 입력창에 포커스, 커서는 글 끝으로
function focusEditInput(kind, id) {
  const target = listsEl.querySelector(`${itemSelector(kind, id)} [data-action="edit-text"]`);
  if (!target) return;
  target.focus();
  target.setSelectionRange(target.value.length, target.value.length);
}

function beginEdit(kind, id) {
  startEdit(kind, id);
  focusEditInput(kind, id);
}

async function endEdit(kind, id, shouldSave) {
  if (shouldSave) {
    if (!(await saveEdit())) {
      // 반복 설정을 고치던 중이면 포커스를 옮기지 않는다
      if (!listsEl.contains(document.activeElement)) focusEditInput(kind, id);
      return;
    }
  } else {
    cancelEdit();
  }
  restoreFocus(kind, id, 'edit');
}

// 키워드가 가장 많이 맞은 카테고리 (안 맞거나 동점이면 null)
function guessCategory(text) {
  const lower = text.toLowerCase();
  let best = null;
  let bestScore = 0;
  let isTie = false;
  CATEGORY_VALUES.forEach((category) => {
    const score = CATEGORY_KEYWORDS[category].filter((word) => lower.includes(word)).length;
    if (score > bestScore) {
      best = category;
      bestScore = score;
      isTie = false;
    } else if (score > 0 && score === bestScore) {
      isTie = true;
    }
  });
  return isTie ? null : best;
}

// ---------- 이벤트 ----------

// 입력하는 동안 카테고리 선택칸을 자동으로 바꾼다
input.addEventListener('input', () => {
  if (categoryLocked) return;
  const guess = guessCategory(input.value);
  if (!guess) return;
  categorySelect.value = guess;
  categorySelect.classList.add('is-auto');
});

categorySelect.addEventListener('change', () => {
  categoryLocked = true;
  categorySelect.classList.remove('is-auto');
});

// 추가: 메모를 골랐으면 그 메모의 품목으로, 반복을 골랐으면 루틴으로, 아니면 할 일로 저장한다
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const memo = selectedMemo === null ? null : findMemo(selectedMemo);
  if (memo) {
    const parsedItems = splitItems(input.value.trim());
    if (parsedItems.error) {
      showNotice(parsedItems.error);
      return;
    }
    if (parsedItems.items.length === 0) {
      input.value = '';
      input.focus();
      return;
    }
    // 저장에 실패하면 입력한 글을 그대로 둔다. 고른 메모는 이어서 넣을 수 있게 남긴다
    if (!(await addMemoItems(memo.id, parsedItems.items.join(', ')))) return;
    input.value = '';
    input.focus();
    return;
  }
  const text = input.value.trim().slice(0, MAX_LENGTH);
  if (text === '') {
    input.value = '';
    input.focus();
    return;
  }
  const parsed = ruleFromState(addRule);
  if (parsed.error) {
    showNotice(parsed.error);
    return;
  }
  // 저장에 실패하면 입력한 글과 반복 설정을 그대로 둔다
  const saved = parsed.rule
    ? await addRoutine(text, categorySelect.value, parsed.rule)
    : await addTodo(text, categorySelect.value);
  if (!saved) return;
  input.value = '';
  categoryLocked = false;
  categorySelect.classList.remove('is-auto');
  resetAddRule();
  input.focus();
});

// ---------- 입력 영역 접기 ----------
// 평소에는 입력창·마이크·추가 한 줄만 보인다. 입력창을 누르거나 적기 시작하면 펼친다.
// (화면을 열 때 커서가 가 있는 것만으로는 펼치지 않는다)

function openAddMore() {
  form.classList.remove('is-collapsed');
  input.setAttribute('aria-expanded', 'true');
}

// 고른 것이 남아 있으면 접지 않는다 (어디에 들어갈지 안 보이면 안 되므로)
function canCloseAddMore() {
  return input.value.trim() === ''
    && selectedMemo === null
    && addRule.type === 'none';
}

function closeAddMore() {
  if (!canCloseAddMore()) return;
  form.classList.add('is-collapsed');
  input.setAttribute('aria-expanded', 'false');
}

input.setAttribute('aria-controls', 'add-more');
input.setAttribute('aria-expanded', 'false');
input.addEventListener('click', openAddMore);
input.addEventListener('input', openAddMore);

// 입력 영역 밖을 누르면 접는다. 누른 동작이 끝난 뒤에 접어서, 목록이 밀려 올라가 엉뚱한 것이 눌리지 않게 한다
document.addEventListener('pointerdown', (event) => {
  if (form.contains(event.target)) return;
  setTimeout(closeAddMore, 350);
});

// 키보드(Tab)로 입력 영역을 벗어났을 때도 접는다
form.addEventListener('focusout', () => {
  setTimeout(() => {
    if (!form.contains(document.activeElement)) closeAddMore();
  }, 350);
});

// 메모 버튼: 누르면 그 메모에 넣는다. "할 일"을 누르거나 고른 메모를 다시 누르면 할 일로 돌아간다
memoBarEl.addEventListener('click', (event) => {
  const chip = event.target.closest('[data-memo]');
  if (!chip) return;
  const picked = chip.dataset.memo === 'none' ? null : Number(chip.dataset.memo);
  selectedMemo = picked === selectedMemo ? null : picked;
  render();
  input.focus();
});

// 탭 선택은 화면 상태만 바꾸므로 저장 없이 다시 그린다
tabsEl.addEventListener('click', (event) => {
  const tab = event.target.closest('.tab');
  if (!tab) return;
  currentFilter = tab.dataset.filter;
  render();
});

statusTabsEl.addEventListener('click', (event) => {
  const tab = event.target.closest('.tab');
  if (!tab) return;
  statusFilter = tab.dataset.status;
  render();
});

clearDoneBtn.addEventListener('click', async () => {
  const doneCount = todos.filter((todo) => todo.done).length;
  if (doneCount === 0) return;
  if (!confirm(`완료한 항목 ${doneCount}개를 모두 지울까요?\n(모든 카테고리의 완료한 할 일이 지워집니다. 루틴과 저장소의 메모는 지워지지 않습니다)`)) return;
  await clearDone();
  input.focus();
});

// 아래는 루틴 목록과 할 일 목록이 함께 쓴다 (항목의 data-kind로 구분)
listsEl.addEventListener('change', async (event) => {
  if (event.target.dataset.action !== 'toggle') return;
  const { kind, id } = event.target.closest('.todo-item').dataset;
  await toggleItem(kind, id);
  restoreFocus(kind, id, 'toggle');
});

// 수정 중 입력값은 화면 상태에 담아 둔다 (다시 그려도 유지)
listsEl.addEventListener('input', (event) => {
  if (!editing) return;
  const action = event.target.dataset.action;
  if (action === 'edit-text') editing.text = event.target.value;
  if (action === 'edit-category') editing.category = event.target.value;
});

// 수정 저장 (Enter 또는 [저장])
listsEl.addEventListener('submit', (event) => {
  event.preventDefault();
  if (editing) endEdit(editing.kind, editing.id, true);
});

// Esc로 수정 취소 (한글 조합 중에는 무시)
listsEl.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || event.isComposing || !editing) return;
  if (!event.target.closest('.is-editing')) return;
  event.preventDefault();
  endEdit(editing.kind, editing.id, false);
});

listsEl.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-action]');
  if (!button || button.tagName !== 'BUTTON') return;
  const { kind, id } = button.closest('.todo-item').dataset;
  const action = button.dataset.action;
  const item = findItem(kind, id);
  if (!item) return;

  if (action === 'edit') beginEdit(kind, id);
  if (action === 'cancel') endEdit(kind, id, false);
  if (action === 'delete') {
    if (!confirm(`이 할 일을 삭제할까요?\n\n${item.text}`)) return;
    await deleteTodo(id);
    input.focus();
  }
  if (action === 'end') {
    if (!confirm(`이 루틴을 종료할까요?\n오늘부터 목록에 나오지 않고, 지난 기록은 남습니다.\n\n${item.text}`)) return;
    await endRoutine(id);
    input.focus();
  }
});

// 데스크톱: 내용을 더블클릭해도 수정
listsEl.addEventListener('dblclick', (event) => {
  const text = event.target.closest('.todo-text');
  if (!text) return;
  const { kind, id } = text.closest('.todo-item').dataset;
  beginEdit(kind, id);
});

logoutBtn.addEventListener('click', async () => {
  try {
    await fetch('api/session', { method: 'DELETE', credentials: 'same-origin' });
  } catch (error) {
    showNotice(CONNECT_ERROR);
    return;
  }
  window.location.href = 'login.html';
});

// 화면에 다시 돌아오면 서버의 목록을 다시 받는다 (자정을 넘긴 경우, 다른 기기에서 바꾼 경우).
// 수정 중이거나 저장 중일 때는 건드리지 않는다.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible' || busy || editing) return;
  load();
});

// 시작: 빈 틀을 먼저 그리고 서버에서 불러온다.
// 입력창에 커서를 두지 않는다. 휴대폰 자판이 바로 떠서 화면을 가리기 때문이다(2026-10-22).
resetAddRule();
render();
load();
