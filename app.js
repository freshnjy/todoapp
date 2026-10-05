'use strict';

const STORAGE_KEY = 'todos';
const LAST_DATE_KEY = 'lastDate';
const MAX_LENGTH = 100;
const CATEGORY_LABELS = { work: '업무', personal: '개인', growth: '성장' };
const CATEGORY_VALUES = Object.keys(CATEGORY_LABELS);

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

// 상태: 할 일 배열, 마지막 접속 날짜 (이 둘만 저장)
let todos = loadTodos();
let lastDate = localStorage.getItem(LAST_DATE_KEY);
// 화면 상태: 선택한 탭, 상태 필터, 수정 중인 항목 { id, text, category } (저장하지 않음)
let currentFilter = 'all';
let statusFilter = 'all';
let editing = null;

// localStorage에서 불러오기 (깨져 있으면 빈 목록)
function loadTodos() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === null) return [];
  try {
    const data = JSON.parse(raw);
    if (!Array.isArray(data)) throw new Error('todos가 배열이 아닙니다.');
    return data;
  } catch (error) {
    console.error('저장된 할 일을 불러오지 못해 빈 목록으로 시작합니다.', error);
    return [];
  }
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
  if (lastDate !== null) localStorage.setItem(LAST_DATE_KEY, lastDate);
}

// 상태 변경 후 항상 이 함수로 저장하고 다시 그린다
function commit() {
  save();
  render();
}

// Date.now() 기반 고유 ID (같은 밀리초에 겹치면 1씩 올림)
function createId() {
  let id = Date.now();
  while (todos.some((todo) => todo.id === String(id))) id += 1;
  return String(id);
}

function normalizeCategory(category) {
  return CATEGORY_VALUES.includes(category) ? category : 'work';
}

function addTodo(text, category) {
  todos.unshift({
    id: createId(),
    text,
    category: normalizeCategory(category),
    done: false,
    createdAt: new Date().toISOString(),
  });
  commit();
}

function deleteTodo(id) {
  todos = todos.filter((todo) => todo.id !== id);
  if (editing && editing.id === id) editing = null;
  commit();
}

// 완료 전환 후 배열 맨 끝으로 옮겨 각 그룹의 맨 아래에 오게 한다
function toggleTodo(id) {
  const index = todos.findIndex((todo) => todo.id === id);
  if (index === -1) return;
  const [todo] = todos.splice(index, 1);
  todo.done = !todo.done;
  todos.push(todo);
  commit();
}

// 완료 항목 일괄 삭제 (모든 카테고리)
function clearDone() {
  todos = todos.filter((todo) => !todo.done);
  if (editing && !todos.some((todo) => todo.id === editing.id)) editing = null;
  commit();
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

// 빈 값이면 저장하지 않고 수정 상태를 유지한다
function saveEdit() {
  if (!editing) return false;
  const text = editing.text.trim().slice(0, MAX_LENGTH);
  if (text === '') return false;
  const todo = todos.find((item) => item.id === editing.id);
  if (todo) {
    todo.text = text;
    todo.category = normalizeCategory(editing.category);
  }
  editing = null;
  commit();
  return true;
}

// 오늘 날짜 YYYY-MM-DD (기기 현지 시간, toISOString은 UTC라 쓰지 않음)
function getTodayString() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

// 날짜가 바뀌었으면 완료 항목만 지운다 (처음 쓰는 날은 날짜만 기록)
function cleanUpIfNewDay() {
  const today = getTodayString();
  if (lastDate === today) return false;
  if (lastDate !== null) {
    todos = todos.filter((todo) => !todo.done);
    if (editing && !todos.some((todo) => todo.id === editing.id)) editing = null;
  }
  lastDate = today;
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
  li.className = todo.done ? 'todo-item is-done' : 'todo-item';
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
  badge.className = `badge badge-${todo.category}`;
  badge.textContent = CATEGORY_LABELS[todo.category] ?? CATEGORY_LABELS.work;

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
  li.className = 'todo-item is-editing';
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

// 선택한 탭 기준 진행률 (상태 필터와 상관없이 카테고리 기준)
function renderProgress(visible) {
  const total = visible.length;
  const doneCount = visible.filter((todo) => todo.done).length;
  const percent = total === 0 ? 0 : Math.round((doneCount / total) * 100);

  progressFill.style.width = `${percent}%`;
  progressBar.setAttribute('aria-valuenow', String(percent));
  progressText.textContent = total === 0
    ? '아직 할 일이 없어요 (0%)'
    : `${doneCount} / ${total} 완료 (${percent}%)`;
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
  emptyEl.textContent = visible.length === 0
    ? '오늘 할 일을 추가해 보세요'
    : '해당하는 할 일이 없어요';
  clearDoneBtn.hidden = !todos.some((todo) => todo.done);

  renderTabs();
  renderStatusTabs();
  renderProgress(visible);
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

function endEdit(id, shouldSave) {
  if (shouldSave) {
    if (!saveEdit()) {
      focusEditInput(id);
      return;
    }
  } else {
    cancelEdit();
  }
  restoreFocus(id, 'edit');
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = input.value.trim().slice(0, MAX_LENGTH);
  if (text === '') {
    input.value = '';
    input.focus();
    return;
  }
  addTodo(text, categorySelect.value);
  input.value = '';
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

clearDoneBtn.addEventListener('click', () => {
  const doneCount = todos.filter((todo) => todo.done).length;
  if (doneCount === 0) return;
  if (!confirm(`완료한 할 일 ${doneCount}개를 모두 지울까요?\n(모든 카테고리의 완료 항목이 지워집니다)`)) return;
  clearDone();
  input.focus();
});

listEl.addEventListener('change', (event) => {
  if (event.target.dataset.action !== 'toggle') return;
  const id = event.target.closest('.todo-item').dataset.id;
  toggleTodo(id);
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

listEl.addEventListener('click', (event) => {
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
    deleteTodo(id);
    input.focus();
  }
});

// 데스크톱: 내용을 더블클릭해도 수정
listEl.addEventListener('dblclick', (event) => {
  const text = event.target.closest('.todo-text');
  if (!text) return;
  beginEdit(text.closest('.todo-item').dataset.id);
});

// 화면에 다시 돌아오면 날짜 확인 (자정을 넘겨 켜 둔 경우)
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return;
  if (cleanUpIfNewDay()) commit();
});

// 시작: 날짜 확인 → 저장 → 그리기
cleanUpIfNewDay();
commit();
