'use strict';

const MAX_LENGTH = 100;
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

const todayEl = document.getElementById('today');
const form = document.getElementById('add-form');
const input = document.getElementById('add-input');
const categorySelect = document.getElementById('add-category');
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
const statsListEl = document.getElementById('stats-list');
const noticeEl = document.getElementById('notice');
const logoutBtn = document.getElementById('logout');

const CONNECT_ERROR = '서버와 연결하지 못했어요. 잠시 후 다시 시도해 주세요.';

// 상태: 서버에서 받은 할 일 배열. 저장은 서버가 한다 (docs/api.md)
let todos = [];
// 처음 불러오기가 끝났는지 (끝나기 전에는 "불러오는 중"을 보여 준다)
let loaded = false;
// 서버에 바꾸는 중인지 (끝날 때까지 다른 변경을 받지 않는다)
let busy = false;
// 화면 상태: 선택한 탭, 상태 필터, 수정 중인 항목 { id, text, category } (저장하지 않음)
let currentFilter = 'all';
let statusFilter = 'all';
let editing = null;
// 사용자가 카테고리를 직접 고르면 이번 할 일은 자동 분류를 멈춘다
let categoryLocked = false;

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
  if (!response.ok) throw new Error(`서버 응답 ${response.status}`);
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

// 서버의 목록으로 화면을 다시 그린다 (날짜가 바뀌어 정리된 것, 다른 기기에서 바꾼 것 포함)
async function refresh() {
  const data = await api('GET', 'api/todos');
  todos = data.todos.map((todo) => ({
    id: String(todo.id),
    text: todo.text,
    category: todo.category,
    done: todo.done,
  }));
  if (editing && !todos.some((todo) => todo.id === editing.id)) editing = null;
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

function addTodo(text, category) {
  return change(() => api('POST', 'api/todos', { text, category: normalizeCategory(category) }));
}

function deleteTodo(id) {
  return change(() => api('DELETE', `api/todos/${id}`));
}

// 완료 전환. 서버가 그 항목을 맨 끝으로 옮겨 각 그룹의 맨 아래에 오게 한다
function toggleTodo(id) {
  const todo = todos.find((item) => item.id === id);
  if (!todo) return Promise.resolve(false);
  return change(() => api('PATCH', `api/todos/${id}`, { done: !todo.done }));
}

// 완료 항목 일괄 삭제 (모든 카테고리)
function clearDone() {
  return change(() => api('POST', 'api/todos/clear-done'));
}

// 수정 시작 (한 번에 한 항목만)
function startEdit(id) {
  const todo = todos.find((item) => item.id === id);
  if (!todo) return;
  editing = { id, text: todo.text, category: todo.category };
  render();
}

function cancelEdit() {
  editing = null;
  render();
}

// 빈 값이거나 저장에 실패하면 수정 상태를 유지한다
async function saveEdit() {
  if (!editing) return false;
  const { id } = editing;
  const text = editing.text.trim().slice(0, MAX_LENGTH);
  if (text === '') return false;
  const category = normalizeCategory(editing.category);
  const saved = await change(() => api('PATCH', `api/todos/${id}`, { text, category }));
  if (!saved) return false;
  if (editing && editing.id === id) editing = null;
  render();
  return true;
}

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

function createTodoItem(todo) {
  const li = document.createElement('li');
  li.className = `todo-item cat-${normalizeCategory(todo.category)}`;
  if (todo.done) li.classList.add('is-done');
  li.dataset.id = todo.id;

  const label = document.createElement('label');
  label.className = 'todo-check';
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = todo.done;
  checkbox.dataset.action = 'toggle';
  checkbox.setAttribute('aria-label', `${todo.text} 완료 표시`);
  label.append(checkbox);

  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.textContent = CATEGORY_LABELS[normalizeCategory(todo.category)];

  const text = document.createElement('span');
  text.className = 'todo-text';
  text.textContent = todo.text;

  const actions = document.createElement('div');
  actions.className = 'todo-actions';
  actions.append(
    createButton('수정', 'edit', `${todo.text} 수정`),
    createButton('삭제', 'delete', `${todo.text} 삭제`, 'btn-danger'),
  );

  li.append(label, badge, text, actions);
  return li;
}

// 수정 중인 항목: 그 자리에 입력창 + 카테고리 + 저장/취소
function createEditItem(todo) {
  const li = document.createElement('li');
  li.className = `todo-item is-editing cat-${normalizeCategory(editing.category)}`;
  li.dataset.id = todo.id;

  const editForm = document.createElement('form');
  editForm.className = 'edit-form';

  const editInput = document.createElement('input');
  editInput.type = 'text';
  editInput.className = 'add-input';
  editInput.maxLength = MAX_LENGTH;
  editInput.autocomplete = 'off';
  editInput.value = editing.text;
  editInput.dataset.action = 'edit-text';
  editInput.setAttribute('aria-label', '할 일 내용 수정');

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

  editForm.append(editInput, row);
  li.append(editForm);
  return li;
}

// 탭 버튼: 선택 표시와 카테고리별 개수
function renderTabs() {
  tabsEl.querySelectorAll('.tab').forEach((tab) => {
    const filter = tab.dataset.filter;
    const isActive = filter === currentFilter;
    tab.classList.toggle('is-active', isActive);
    tab.setAttribute('aria-pressed', String(isActive));
    const count = filter === 'all'
      ? todos.length
      : todos.filter((todo) => todo.category === filter).length;
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
  return Math.round((list.filter((todo) => todo.done).length / list.length) * 100);
}

// 통계 카드: 선택한 탭 진행률 (상태 필터와 상관없이 카테고리 기준) + 카테고리별 현황
function renderStats(visible) {
  const total = visible.length;
  const doneCount = visible.filter((todo) => todo.done).length;
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

  statsListEl.querySelectorAll('.stats-row').forEach((row) => {
    const list = todos.filter((todo) => todo.category === row.dataset.category);
    const rowDone = list.filter((todo) => todo.done).length;
    row.querySelector('.mini-fill').style.width = `${getPercent(list)}%`;
    row.querySelector('.stats-count').textContent = `${rowDone} / ${list.length}`;
  });
}

// 화면 전체 다시 그리기: 미완료 → 완료 순, 그룹 안은 배열 순서
function render() {
  todayEl.textContent = formatToday();

  const visible = currentFilter === 'all'
    ? todos
    : todos.filter((todo) => todo.category === currentFilter);
  const ordered = [
    ...(statusFilter === 'done' ? [] : visible.filter((todo) => !todo.done)),
    ...(statusFilter === 'active' ? [] : visible.filter((todo) => todo.done)),
  ];
  listEl.replaceChildren(...ordered.map((todo) => (
    editing && editing.id === todo.id ? createEditItem(todo) : createTodoItem(todo)
  )));
  // 빈 안내: 할 일 자체가 없을 때와 상태 필터로 걸러져 없을 때를 구분
  emptyEl.hidden = ordered.length > 0;
  if (!loaded) emptyEl.textContent = '불러오는 중이에요';
  else if (visible.length === 0) emptyEl.textContent = '오늘 할 일을 추가해 보세요';
  else emptyEl.textContent = '해당하는 할 일이 없어요';
  clearDoneBtn.hidden = !todos.some((todo) => todo.done);

  renderTabs();
  renderStatusTabs();
  renderStats(visible);
}

// 다시 그린 뒤 같은 항목의 같은 컨트롤에 포커스를 되돌린다 (키보드 사용)
function restoreFocus(id, action) {
  const target = listEl.querySelector(`[data-id="${id}"] [data-action="${action}"]`);
  if (target) target.focus();
}

// 수정 입력창에 포커스, 커서는 글 끝으로
function focusEditInput(id) {
  const target = listEl.querySelector(`[data-id="${id}"] [data-action="edit-text"]`);
  if (!target) return;
  target.focus();
  target.setSelectionRange(target.value.length, target.value.length);
}

function beginEdit(id) {
  startEdit(id);
  focusEditInput(id);
}

async function endEdit(id, shouldSave) {
  if (shouldSave) {
    if (!(await saveEdit())) {
      focusEditInput(id);
      return;
    }
  } else {
    cancelEdit();
  }
  restoreFocus(id, 'edit');
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

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = input.value.trim().slice(0, MAX_LENGTH);
  if (text === '') {
    input.value = '';
    input.focus();
    return;
  }
  // 저장에 실패하면 입력한 글을 그대로 둔다
  if (!(await addTodo(text, categorySelect.value))) return;
  input.value = '';
  categoryLocked = false;
  categorySelect.classList.remove('is-auto');
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
  if (!confirm(`완료한 할 일 ${doneCount}개를 모두 지울까요?\n(모든 카테고리의 완료 항목이 지워집니다)`)) return;
  await clearDone();
  input.focus();
});

listEl.addEventListener('change', async (event) => {
  if (event.target.dataset.action !== 'toggle') return;
  const id = event.target.closest('.todo-item').dataset.id;
  await toggleTodo(id);
  restoreFocus(id, 'toggle');
});

// 수정 중 입력값은 화면 상태에 담아 둔다 (다시 그려도 유지)
listEl.addEventListener('input', (event) => {
  if (!editing) return;
  const action = event.target.dataset.action;
  if (action === 'edit-text') editing.text = event.target.value;
  if (action === 'edit-category') editing.category = event.target.value;
});

// 수정 저장 (Enter 또는 [저장])
listEl.addEventListener('submit', (event) => {
  event.preventDefault();
  if (editing) endEdit(editing.id, true);
});

// Esc로 수정 취소 (한글 조합 중에는 무시)
listEl.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || event.isComposing || !editing) return;
  if (!event.target.closest('.is-editing')) return;
  event.preventDefault();
  endEdit(editing.id, false);
});

listEl.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-action]');
  if (!button || button.tagName !== 'BUTTON') return;
  const id = button.closest('.todo-item').dataset.id;
  const action = button.dataset.action;

  if (action === 'edit') beginEdit(id);
  if (action === 'cancel') endEdit(id, false);
  if (action === 'delete') {
    const todo = todos.find((item) => item.id === id);
    if (!todo) return;
    if (!confirm(`이 할 일을 삭제할까요?\n\n${todo.text}`)) return;
    await deleteTodo(id);
    input.focus();
  }
});

// 데스크톱: 내용을 더블클릭해도 수정
listEl.addEventListener('dblclick', (event) => {
  const text = event.target.closest('.todo-text');
  if (!text) return;
  beginEdit(text.closest('.todo-item').dataset.id);
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

// 시작: 빈 틀을 먼저 그리고 서버에서 불러온다
render();
load();
