'use strict';

// 저장소 화면: 그때그때 생각난 것을 메모로 남겨 둔다. 메모 하나에 제목, 글, 품목 목록이 있다.
// 메모는 할 일과 따로 산다. 날짜가 바뀌어도 지우지 않고, 체크한 품목도 표시만 남긴다.
// index.html에서 app.js보다 먼저 불러온다. app.js의 api, showNotice, clearNotice, CONNECT_ERROR와
// habits.js의 currentView, toDate는 함수가 실제로 불릴 때(app.js가 시작한 뒤) 쓴다.

const MEMO_TITLE_MAX_LENGTH = 20;
const MEMO_BODY_MAX_LENGTH = 2000;
const MEMO_ITEMS_TEXT_MAX_LENGTH = 1000;
const MEMO_UNTITLED = '제목 없음';

const viewMemosEl = document.getElementById('view-memos');
const memoNewBtn = document.getElementById('memo-new');
const memoListEl = document.getElementById('memo-list');
const memoEmptyEl = document.getElementById('memo-empty');

// 서버에서 받은 메모 (마지막으로 고친 것이 앞). docs/api.md의 "저장소"
let memos = [];
let memosLoaded = false;
// 서버에 바꾸는 중인지 (끝날 때까지 다른 변경을 받지 않는다)
let memoBusy = false;
// 펼쳐 둔 메모 (저장하지 않음)
const openMemos = new Set();
// 고치는 중인 메모: null | { id: 'new' 또는 메모 id, title, body, items }. 다시 그려도 적던 글이 남게 둔다
let memoDraft = null;
// 고치는 중인 품목: null | { memoId, itemId, text }
let itemDraft = null;
// 메모마다 "품목 추가" 칸에 적던 글
const itemAddDrafts = new Map();

function findMemo(id) {
  return memos.find((memo) => memo.id === id);
}

function memoName(memo) {
  return memo.title || MEMO_UNTITLED;
}

// "2026-10-12T21:40:05+09:00" → "10.12" (올해가 아니면 "2025.10.12")
function memoDateLabel(stamp) {
  const day = stamp.slice(0, 10);
  const date = toDate(day);
  const short = `${date.getUTCMonth() + 1}.${date.getUTCDate()}`;
  const thisYear = (serverToday || day).slice(0, 4);
  return day.slice(0, 4) === thisYear ? short : `${date.getUTCFullYear()}.${short}`;
}

// ---------- 서버 ----------

async function fetchMemos() {
  const data = await api('GET', 'api/memos');
  memos = data.memos;
  memosLoaded = true;
  // 다른 기기에서 지운 메모와 품목은 펼침과 고치는 중에서 뺀다
  [...openMemos].forEach((id) => {
    if (!findMemo(id)) openMemos.delete(id);
  });
  if (memoDraft && memoDraft.id !== 'new' && !findMemo(memoDraft.id)) memoDraft = null;
  if (itemDraft) {
    const memo = findMemo(itemDraft.memoId);
    if (!memo || !memo.items.some((item) => item.id === itemDraft.itemId)) itemDraft = null;
  }
}

// 화면을 바꿨을 때: 받아서 다시 그린다
async function showMemos() {
  try {
    await fetchMemos();
    clearNotice();
  } catch (error) {
    if (!error.unauthorized) showNotice(CONNECT_ERROR);
  }
  renderMemos();
}

// 서버에 바꾼 뒤 목록을 다시 받는다. 성공하면 request의 결과, 실패하면 undefined.
// 입력이 규칙에 맞지 않으면(같은 제목, 빈 메모, 너무 긴 글) 서버가 알려 준 이유를 보여 주고, 적던 글은 그대로 둔다.
async function memoChange(request) {
  if (memoBusy) return undefined;
  memoBusy = true;
  try {
    const result = await request();
    await fetchMemos();
    clearNotice();
    return result === null ? true : result;
  } catch (error) {
    if (error.unauthorized) return undefined;
    showNotice(error.detail && (error.status === 409 || error.status === 422) ? error.detail : CONNECT_ERROR);
    return undefined;
  } finally {
    memoBusy = false;
    renderMemos();
  }
}

// ---------- 그리기 ----------

function memoButton(label, action, ariaLabel, extraClass = '') {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `btn btn-small ${extraClass}`.trim();
  button.dataset.action = action;
  button.textContent = label;
  button.setAttribute('aria-label', ariaLabel);
  return button;
}

// 메모를 만들거나 고치는 칸: 제목, 글, (새 메모면) 품목
function createMemoForm(memo) {
  const isNew = memo === null;
  const li = document.createElement('li');
  li.className = 'memo-card is-editing';
  li.dataset.memoId = isNew ? 'new' : String(memo.id);

  const form = document.createElement('form');
  form.className = 'memo-form';
  form.dataset.role = 'memo-form';

  const title = document.createElement('input');
  title.className = 'add-input memo-title-input';
  title.type = 'text';
  title.maxLength = MEMO_TITLE_MAX_LENGTH;
  title.autocomplete = 'off';
  title.placeholder = '제목 (예: 장보기, 비워 두면 제목 없음)';
  title.value = memoDraft.title;
  title.dataset.field = 'title';
  title.setAttribute('aria-label', '메모 제목');

  const body = document.createElement('textarea');
  body.className = 'add-input memo-body-input';
  body.rows = 3;
  body.maxLength = MEMO_BODY_MAX_LENGTH;
  body.placeholder = '적어 둘 글';
  body.value = memoDraft.body;
  body.dataset.field = 'body';
  body.setAttribute('aria-label', '메모 글');

  form.append(title, body);

  if (isNew) {
    const items = document.createElement('input');
    items.className = 'add-input';
    items.type = 'text';
    items.maxLength = MEMO_ITEMS_TEXT_MAX_LENGTH;
    items.autocomplete = 'off';
    items.placeholder = '품목 (쉼표로 여러 개: 우유, 소고기)';
    items.value = memoDraft.items;
    items.dataset.field = 'items';
    items.setAttribute('aria-label', '품목');
    form.append(items);
  }

  const row = document.createElement('div');
  row.className = 'add-row';
  const save = document.createElement('button');
  save.type = 'submit';
  save.className = 'btn btn-primary';
  save.textContent = isNew ? '만들기' : '저장';
  row.append(save, memoButton('취소', 'memo-cancel', '메모 고치기 취소'));
  form.append(row);

  li.append(form);
  return li;
}

// 품목 한 줄: 체크박스 + 내용 (+ 넣은 날) + 수정·삭제. 체크해도 자리는 그대로다
function createMemoItem(memo, item) {
  const li = document.createElement('li');
  li.className = 'memo-item';
  if (item.done) li.classList.add('is-done');
  li.dataset.itemId = String(item.id);

  if (itemDraft && itemDraft.memoId === memo.id && itemDraft.itemId === item.id) {
    li.classList.add('is-editing');
    const form = document.createElement('form');
    form.className = 'memo-item-form';
    form.dataset.role = 'item-form';
    const input = document.createElement('input');
    input.className = 'add-input';
    input.type = 'text';
    input.maxLength = MAX_LENGTH;
    input.autocomplete = 'off';
    input.value = itemDraft.text;
    input.dataset.field = 'item-text';
    input.setAttribute('aria-label', `${item.text} 고치기`);
    const save = document.createElement('button');
    save.type = 'submit';
    save.className = 'btn btn-small btn-primary';
    save.textContent = '저장';
    form.append(input, save, memoButton('취소', 'item-cancel', '품목 고치기 취소'));
    li.append(form);
    return li;
  }

  // 글자를 눌러도 체크된다 (가게에서 한 손으로 누르기 쉽게)
  const label = document.createElement('label');
  label.className = 'memo-check';
  const box = document.createElement('span');
  box.className = 'todo-check';
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = item.done;
  checkbox.dataset.action = 'item-toggle';
  box.append(checkbox);
  const text = document.createElement('span');
  text.className = 'todo-text';
  text.textContent = item.text;
  label.append(box, text);

  // 넣은 날: 메모를 만든 날과 다를 때만 적는다 (같은 날이면 모두 같은 날짜라 군더더기다)
  const added = memoDateLabel(item.created_at);
  if (item.created_at.slice(0, 10) !== memo.created_at.slice(0, 10)) {
    const date = document.createElement('span');
    date.className = 'memo-item-date';
    date.textContent = added;
    label.append(date);
  }
  checkbox.setAttribute('aria-label', `${item.text}, 넣은 날 ${added}, 체크`);

  const actions = document.createElement('div');
  actions.className = 'todo-actions';
  actions.append(
    memoButton('수정', 'item-edit', `${item.text} 수정`),
    memoButton('✕', 'item-delete', `${item.text} 삭제`, 'btn-danger'),
  );

  li.append(label, actions);
  return li;
}

// 메모 한 칸. 접혀 있으면 제목·남은 품목 수·날짜와 글의 첫 줄만, 펼치면 전부
function createMemoCard(memo) {
  const isOpen = openMemos.has(memo.id);
  const left = memo.items.filter((item) => !item.done).length;
  const name = memoName(memo);

  const li = document.createElement('li');
  li.className = 'memo-card';
  if (isOpen) li.classList.add('is-open');
  li.dataset.memoId = String(memo.id);

  const head = document.createElement('button');
  head.type = 'button';
  head.className = 'memo-head';
  head.dataset.action = 'memo-open';
  head.setAttribute('aria-expanded', String(isOpen));
  const countLabel = memo.items.length > 0 ? `, 남은 품목 ${left}개` : '';
  head.setAttribute('aria-label', `${name}${countLabel}, 고친 날 ${memoDateLabel(memo.updated_at)}, ${isOpen ? '접기' : '펼치기'}`);

  const line = document.createElement('span');
  line.className = 'memo-line';
  const arrow = document.createElement('span');
  arrow.className = 'group-arrow';
  arrow.textContent = isOpen ? '▾' : '▸';
  const title = document.createElement('span');
  title.className = 'memo-title';
  if (!memo.title) title.classList.add('is-untitled');
  title.textContent = name;
  line.append(arrow, title);
  if (memo.items.length > 0) {
    const count = document.createElement('span');
    count.className = 'memo-count';
    count.textContent = `(${left})`;
    line.append(count);
  }
  const date = document.createElement('span');
  date.className = 'memo-date';
  date.textContent = memoDateLabel(memo.updated_at);
  line.append(date);
  head.append(line);

  // 접혀 있을 때의 미리 보기: 글의 첫 줄, 글이 없으면 남은 품목
  if (!isOpen) {
    const firstLine = memo.body.split('\n').find((part) => part.trim()) || '';
    const preview = firstLine || memo.items.filter((item) => !item.done).map((item) => item.text).join(', ');
    if (preview) {
      const previewEl = document.createElement('span');
      previewEl.className = 'memo-preview';
      previewEl.textContent = preview;
      head.append(previewEl);
    }
  }
  li.append(head);
  if (!isOpen) return li;

  const inside = document.createElement('div');
  inside.className = 'memo-inside';

  if (memo.body) {
    const body = document.createElement('p');
    body.className = 'memo-body';
    body.textContent = memo.body;
    inside.append(body);
  }

  if (memo.items.length > 0) {
    const list = document.createElement('ul');
    list.className = 'memo-items';
    list.append(...memo.items.map((item) => createMemoItem(memo, item)));
    inside.append(list);
  }

  // 품목 넣기: 쉼표로 여러 개
  const add = document.createElement('form');
  add.className = 'memo-add';
  add.dataset.role = 'item-add';
  const addInput = document.createElement('input');
  addInput.className = 'add-input';
  addInput.type = 'text';
  addInput.maxLength = MEMO_ITEMS_TEXT_MAX_LENGTH;
  addInput.autocomplete = 'off';
  addInput.placeholder = '품목 추가 (쉼표로 여러 개)';
  addInput.value = itemAddDrafts.get(memo.id) || '';
  addInput.dataset.field = 'item-add';
  addInput.setAttribute('aria-label', `${name}에 품목 추가`);
  const addBtn = document.createElement('button');
  addBtn.type = 'submit';
  addBtn.className = 'btn btn-primary';
  addBtn.textContent = '추가';
  add.append(addInput, addBtn);
  inside.append(add);

  const foot = document.createElement('div');
  foot.className = 'memo-foot';
  const meta = document.createElement('span');
  meta.className = 'memo-meta';
  meta.textContent = `만든 날 ${memoDateLabel(memo.created_at)} · 고친 날 ${memoDateLabel(memo.updated_at)}`;
  const tools = document.createElement('div');
  tools.className = 'todo-actions';
  if (memo.items.some((item) => item.done)) {
    tools.append(memoButton('체크한 품목 지우기', 'memo-clear-done', `${name}의 체크한 품목 지우기`, 'btn-danger'));
  }
  tools.append(
    memoButton('수정', 'memo-edit', `${name} 메모 수정`),
    memoButton('삭제', 'memo-delete', `${name} 메모 삭제`, 'btn-danger'),
  );
  foot.append(meta, tools);
  inside.append(foot);

  li.append(inside);
  return li;
}

// 저장소 화면 다시 그리기. habits.js의 renderHabits()가 화면을 바꿀 때 부른다
function renderMemos() {
  viewMemosEl.hidden = currentView !== 'memos';
  if (currentView !== 'memos') return;

  const rows = [];
  if (memoDraft && memoDraft.id === 'new') rows.push(createMemoForm(null));
  memos.forEach((memo) => {
    rows.push(memoDraft && memoDraft.id === memo.id ? createMemoForm(memo) : createMemoCard(memo));
  });
  memoListEl.replaceChildren(...rows);
  memoNewBtn.hidden = Boolean(memoDraft && memoDraft.id === 'new');

  memoEmptyEl.hidden = memos.length > 0 || Boolean(memoDraft);
  memoEmptyEl.textContent = memosLoaded
    ? '아직 메모가 없어요. 생각난 것을 적어 두면 여기에 남아요.'
    : '불러오는 중이에요';
}

// 다시 그린 뒤 같은 자리에 커서를 둔다
function focusInMemo(memoId, selector) {
  const card = memoListEl.querySelector(`.memo-card[data-memo-id="${memoId}"]`);
  const target = card && card.querySelector(selector);
  if (target) target.focus();
}

// ---------- 동작 ----------

function startMemoDraft(memo) {
  memoDraft = memo
    ? { id: memo.id, title: memo.title || '', body: memo.body, items: '' }
    : { id: 'new', title: '', body: '', items: '' };
  itemDraft = null;
  renderMemos();
  focusInMemo(memo ? memo.id : 'new', '[data-field="title"]');
}

async function saveMemoDraft() {
  const draft = memoDraft;
  if (draft.id === 'new') {
    const created = await memoChange(() => api('POST', 'api/memos', {
      title: draft.title,
      body: draft.body,
      items: draft.items,
    }));
    if (!created) return;
    memoDraft = null;
    // 만든 메모를 펼쳐서 바로 이어 쓸 수 있게
    openMemos.add(created.id);
    renderMemos();
    focusInMemo(created.id, '[data-field="item-add"]');
    return;
  }
  const saved = await memoChange(() => api('PATCH', `api/memos/${draft.id}`, {
    title: draft.title,
    body: draft.body,
  }));
  if (!saved) return;
  memoDraft = null;
  renderMemos();
  focusInMemo(draft.id, '.memo-head');
}

function cancelMemoDraft() {
  const id = memoDraft ? memoDraft.id : null;
  memoDraft = null;
  clearNotice();
  renderMemos();
  if (id === 'new') memoNewBtn.focus();
  else if (id !== null) focusInMemo(id, '.memo-head');
}

memoNewBtn.addEventListener('click', () => startMemoDraft(null));

memoListEl.addEventListener('input', (event) => {
  const field = event.target.dataset.field;
  if (!field) return;
  const card = event.target.closest('.memo-card');
  if (field === 'item-add') itemAddDrafts.set(Number(card.dataset.memoId), event.target.value);
  else if (field === 'item-text' && itemDraft) itemDraft.text = event.target.value;
  else if (memoDraft && field in memoDraft) memoDraft[field] = event.target.value;
});

memoListEl.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.target;
  const card = form.closest('.memo-card');
  const role = form.dataset.role;

  if (role === 'memo-form') {
    await saveMemoDraft();
    return;
  }

  const memoId = Number(card.dataset.memoId);
  if (role === 'item-add') {
    const text = (itemAddDrafts.get(memoId) || '').trim();
    if (!text) {
      focusInMemo(memoId, '[data-field="item-add"]');
      return;
    }
    const added = await memoChange(() => api('POST', `api/memos/${memoId}/items`, { text }));
    if (added) itemAddDrafts.delete(memoId);
    renderMemos();
    // 이어서 넣을 수 있게 커서를 그대로 둔다
    focusInMemo(memoId, '[data-field="item-add"]');
    return;
  }

  if (role === 'item-form' && itemDraft) {
    const { itemId, text } = itemDraft;
    const saved = await memoChange(() => api('PATCH', `api/memos/${memoId}/items/${itemId}`, { text }));
    if (!saved) return;
    itemDraft = null;
    renderMemos();
    focusInMemo(memoId, `.memo-item[data-item-id="${itemId}"] input[type="checkbox"]`);
  }
});

memoListEl.addEventListener('change', async (event) => {
  if (event.target.dataset.action !== 'item-toggle') return;
  const card = event.target.closest('.memo-card');
  const row = event.target.closest('.memo-item');
  const memoId = Number(card.dataset.memoId);
  const itemId = Number(row.dataset.itemId);
  await memoChange(() => api('PATCH', `api/memos/${memoId}/items/${itemId}`, { done: event.target.checked }));
  focusInMemo(memoId, `.memo-item[data-item-id="${itemId}"] input[type="checkbox"]`);
});

memoListEl.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const card = button.closest('.memo-card');
  const action = button.dataset.action;

  if (action === 'memo-cancel') {
    cancelMemoDraft();
    return;
  }
  if (action === 'item-cancel') {
    const memoId = itemDraft ? itemDraft.memoId : null;
    const itemId = itemDraft ? itemDraft.itemId : null;
    itemDraft = null;
    clearNotice();
    renderMemos();
    if (memoId !== null) focusInMemo(memoId, `.memo-item[data-item-id="${itemId}"] input[type="checkbox"]`);
    return;
  }

  const memo = findMemo(Number(card.dataset.memoId));
  if (!memo) return;

  if (action === 'memo-open') {
    if (openMemos.has(memo.id)) openMemos.delete(memo.id);
    else openMemos.add(memo.id);
    renderMemos();
    focusInMemo(memo.id, '.memo-head');
  } else if (action === 'memo-edit') {
    startMemoDraft(memo);
  } else if (action === 'memo-delete') {
    const count = memo.items.length;
    const message = count > 0
      ? `'${memoName(memo)}' 메모를 지울까요? 품목 ${count}개도 함께 지워져요.`
      : `'${memoName(memo)}' 메모를 지울까요?`;
    if (!window.confirm(message)) return;
    await memoChange(() => api('DELETE', `api/memos/${memo.id}`));
    memoNewBtn.focus();
  } else if (action === 'memo-clear-done') {
    await memoChange(() => api('POST', `api/memos/${memo.id}/clear-done`));
    focusInMemo(memo.id, '[data-field="item-add"]');
  } else if (action === 'item-edit' || action === 'item-delete') {
    const itemId = Number(button.closest('.memo-item').dataset.itemId);
    const item = memo.items.find((entry) => entry.id === itemId);
    if (!item) return;
    if (action === 'item-delete') {
      await memoChange(() => api('DELETE', `api/memos/${memo.id}/items/${itemId}`));
      focusInMemo(memo.id, '[data-field="item-add"]');
      return;
    }
    itemDraft = { memoId: memo.id, itemId, text: item.text };
    renderMemos();
    focusInMemo(memo.id, '[data-field="item-text"]');
  }
});

// Esc: 고치던 것을 그만둔다
memoListEl.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  if (event.target.dataset.field === 'item-text') {
    event.target.closest('.memo-item').querySelector('[data-action="item-cancel"]').click();
  } else if (memoDraft && ['title', 'body', 'items'].includes(event.target.dataset.field)) {
    cancelMemoDraft();
  }
});
