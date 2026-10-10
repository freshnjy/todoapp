'use strict';

// 습관(해빗트래커) 화면: 루틴별로 한 날, 안 한 날, 쉬는 날을 주간·월간으로 보여 주고 바로 고친다.
// 한 날에는 색 동그라미 도장을 찍는다. 안 한 날은 빈칸으로 둔다.
// index.html에서 app.js보다 먼저 불러온다. app.js의 api, change, showNotice, serverToday 등은
// 함수가 실제로 불릴 때(app.js가 시작한 뒤) 쓰므로 순서가 달라도 괜찮다.

const HABIT_WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']; // 0=월 ... 6=일
const HABIT_STATUS = {
  done: { symbol: '✓', label: '한 날' },
  missed: { symbol: '', label: '안 한 날' },
  pending: { symbol: '', label: '오늘, 아직 안 함' },
  off: { symbol: '–', label: '쉬는 날' },
  upcoming: { symbol: '', label: '아직 오지 않은 날' },
};

const viewTabsEl = document.getElementById('view-tabs');
const viewTodayEl = document.getElementById('view-today');
const viewHabitsEl = document.getElementById('view-habits');
const habitModesEl = document.getElementById('habit-modes');
const habitPrevBtn = document.getElementById('habit-prev');
const habitNextBtn = document.getElementById('habit-next');
const habitPeriodEl = document.getElementById('habit-period');
const habitListEl = document.getElementById('habit-list');
const habitEmptyEl = document.getElementById('habit-empty');
const habitLegendEl = document.getElementById('habit-legend');

// 보고 있는 화면: 'today' | 'habits'
let currentView = 'today';
// 보기 기간: 'week' | 'month'
let habitMode = 'week';
// 보고 있는 기간 안의 하루 (YYYY-MM-DD). null이면 서버의 오늘이 든 기간
let habitAnchor = null;
// 마지막으로 받은 api/habits 응답 { today, start, end, routines }
let habitData = null;

// ---------- 날짜 계산 (기기 시간대와 상관없게 UTC 자정으로 다룬다) ----------

function toDate(text) {
  const [year, month, day] = text.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function toText(date) {
  return date.toISOString().slice(0, 10);
}

function addDays(text, count) {
  const date = toDate(text);
  date.setUTCDate(date.getUTCDate() + count);
  return toText(date);
}

function weekdayOf(text) {
  return (toDate(text).getUTCDay() + 6) % 7;
}

function monthStart(text, monthOffset = 0) {
  const date = toDate(text);
  return toText(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + monthOffset, 1)));
}

// 보고 있는 기간: 주간은 월요일~일요일, 월간은 1일~말일
function habitRange() {
  const anchor = habitAnchor || serverToday;
  if (habitMode === 'week') {
    const start = addDays(anchor, -weekdayOf(anchor));
    return { start, end: addDays(start, 6) };
  }
  const start = monthStart(anchor);
  return { start, end: addDays(monthStart(anchor, 1), -1) };
}

function habitPeriodLabel(range) {
  const start = toDate(range.start);
  const end = toDate(range.end);
  if (habitMode === 'month') return `${start.getUTCFullYear()}년 ${start.getUTCMonth() + 1}월`;
  const endText = start.getUTCMonth() === end.getUTCMonth()
    ? `${end.getUTCDate()}일`
    : `${end.getUTCMonth() + 1}월 ${end.getUTCDate()}일`;
  return `${start.getUTCMonth() + 1}월 ${start.getUTCDate()}일 ~ ${endText}`;
}

// ---------- 서버 ----------

// 보고 있는 기간의 기록을 받는다. 오류는 부른 쪽이 처리한다
async function fetchHabits() {
  if (!serverToday) return;
  const { start, end } = habitRange();
  habitData = await api('GET', `api/habits?start=${start}&end=${end}`);
}

// 기간이나 화면을 바꿨을 때: 받아서 다시 그린다
async function showHabits() {
  try {
    await fetchHabits();
    clearNotice();
  } catch (error) {
    if (!error.unauthorized) showNotice(CONNECT_ERROR);
  }
  renderHabits();
}

// ---------- 그리기 ----------

// 하루 칸. 하는 날(한 날, 안 한 날, 오늘)은 누를 수 있는 버튼, 나머지는 글자만.
// 한 날은 색만이 아니라 모양(동그라미)으로도 구분한다.
// showDate가 true면 칸 안에 날짜를 적는다 (월간). 주간은 동그라미 안에 ✓를 넣는다
function createHabitMark(routine, day, status, showDate) {
  const clickable = status === 'done' || status === 'missed' || status === 'pending';
  const mark = document.createElement(clickable ? 'button' : 'span');
  mark.className = `habit-mark is-${status}`;
  if (day === habitData.today) mark.classList.add('is-today');

  const date = toDate(day);
  const label = `${date.getUTCMonth() + 1}월 ${date.getUTCDate()}일 ${HABIT_WEEKDAYS[weekdayOf(day)]}요일`;
  if (clickable) {
    mark.type = 'button';
    mark.dataset.id = String(routine.id);
    mark.dataset.day = day;
    mark.dataset.done = String(status === 'done');
    mark.setAttribute('aria-pressed', String(status === 'done'));
    mark.setAttribute('aria-label', `${routine.text}, ${label}: ${HABIT_STATUS[status].label}`);
  } else {
    mark.setAttribute('role', 'img');
    mark.setAttribute('aria-label', `${label}: ${HABIT_STATUS[status].label}`);
  }

  if (showDate) {
    const number = document.createElement('span');
    number.className = 'habit-num';
    number.textContent = String(date.getUTCDate());
    mark.append(number);
  }
  const symbol = document.createElement('span');
  symbol.className = 'habit-sym';
  symbol.textContent = HABIT_STATUS[status].symbol;
  mark.append(symbol);
  return mark;
}

// 주간: 요일과 날짜를 위에 적은 일곱 칸
function createWeekGrid(routine) {
  const grid = document.createElement('div');
  grid.className = 'habit-grid habit-week';
  routine.days.forEach((status, index) => {
    const day = addDays(habitData.start, index);
    const cell = document.createElement('div');
    cell.className = 'habit-day';
    const head = document.createElement('span');
    head.className = 'habit-dow';
    head.textContent = `${HABIT_WEEKDAYS[index]} ${toDate(day).getUTCDate()}`;
    head.setAttribute('aria-hidden', 'true');
    cell.append(head, createHabitMark(routine, day, status, false));
    grid.append(cell);
  });
  return grid;
}

// 월간: 1일부터 번호순으로 늘어놓는다. 한 줄의 칸 수는 화면 폭에 따라 CSS가 정한다 (좁으면 8칸, 넓으면 16칸)
function createMonthGrid(routine) {
  const grid = document.createElement('div');
  grid.className = 'habit-grid habit-month';
  routine.days.forEach((status, index) => {
    grid.append(createHabitMark(routine, addDays(habitData.start, index), status, true));
  });
  return grid;
}

function createHabitCard(routine) {
  const li = document.createElement('li');
  li.className = `card habit-card cat-${normalizeCategory(routine.category)}`;
  if (routine.ended) li.classList.add('is-ended');

  const head = document.createElement('div');
  head.className = 'habit-head';

  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.textContent = CATEGORY_LABELS[normalizeCategory(routine.category)];

  const main = document.createElement('div');
  main.className = 'todo-main';
  const text = document.createElement('span');
  text.className = 'todo-text';
  text.textContent = routine.text;
  const rule = document.createElement('span');
  rule.className = 'todo-rule';
  rule.textContent = routine.ended ? `${ruleLabel(routine.rule)} · 종료함` : ruleLabel(routine.rule);
  main.append(text, rule);

  // 지표: 연속 달성일(종료한 루틴은 빼고)과 이 기간의 달성 수
  const metrics = document.createElement('div');
  metrics.className = 'habit-metrics';
  if (!routine.ended) {
    const streak = document.createElement('span');
    streak.className = 'habit-streak';
    streak.textContent = `연속 ${routine.streak}일`;
    metrics.append(streak);
  }
  const rate = document.createElement('span');
  rate.className = 'habit-rate';
  rate.textContent = routine.due === 0
    ? '달성 –'
    : `달성 ${routine.done}/${routine.due} (${Math.round((routine.done / routine.due) * 100)}%)`;
  metrics.append(rate);

  head.append(badge, main, metrics);
  li.append(head, habitMode === 'week' ? createWeekGrid(routine) : createMonthGrid(routine));
  return li;
}

// 습관 화면 다시 그리기. app.js의 render()가 끝에서 부른다
function renderHabits() {
  viewTabsEl.querySelectorAll('.tab').forEach((tab) => {
    const isActive = tab.dataset.view === currentView;
    tab.classList.toggle('is-active', isActive);
    tab.setAttribute('aria-pressed', String(isActive));
  });
  viewTodayEl.hidden = currentView !== 'today';
  viewHabitsEl.hidden = currentView !== 'habits';
  if (currentView !== 'habits' || !serverToday) return;

  habitModesEl.querySelectorAll('.tab').forEach((tab) => {
    const isActive = tab.dataset.mode === habitMode;
    tab.classList.toggle('is-active', isActive);
    tab.setAttribute('aria-pressed', String(isActive));
  });

  const range = habitRange();
  habitPeriodEl.textContent = habitPeriodLabel(range);
  // 오늘이 든 기간보다 뒤로는 넘기지 않는다
  habitNextBtn.disabled = range.end >= serverToday;

  // 받아 둔 기록이 지금 보는 기간의 것일 때만 그린다 (기간을 넘기는 중이면 비워 둔다)
  const ready = habitData !== null && habitData.start === range.start && habitData.end === range.end;
  const shown = ready ? habitData.routines : [];
  habitListEl.replaceChildren(...shown.map(createHabitCard));
  habitEmptyEl.hidden = shown.length > 0;
  habitLegendEl.hidden = shown.length === 0;
  if (!ready) habitEmptyEl.textContent = '불러오는 중이에요';
  else if (routines.length === 0) habitEmptyEl.textContent = '아직 루틴이 없어요. ‘오늘’ 화면에서 반복을 골라 할 일을 추가하면 여기에 나와요.';
  else habitEmptyEl.textContent = '이 기간에는 루틴이 없었어요';
}

// ---------- 이벤트 ----------

viewTabsEl.addEventListener('click', (event) => {
  const tab = event.target.closest('.tab');
  if (!tab || tab.dataset.view === currentView) return;
  currentView = tab.dataset.view;
  renderHabits();
  // 화면을 바꿀 때마다 서버의 최신 상태를 받는다 (습관 화면에서 고친 것이 오늘 화면에도 보이게)
  if (currentView === 'habits') showHabits();
  else load();
});

habitModesEl.addEventListener('click', (event) => {
  const tab = event.target.closest('.tab');
  if (!tab || tab.dataset.mode === habitMode) return;
  habitMode = tab.dataset.mode;
  // 기간 종류를 바꾸면 오늘이 든 기간으로 돌아온다
  habitAnchor = null;
  showHabits();
});

function shiftHabitPeriod(step) {
  const range = habitRange();
  habitAnchor = habitMode === 'week' ? addDays(range.start, 7 * step) : monthStart(range.start, step);
  showHabits();
}

habitPrevBtn.addEventListener('click', () => shiftHabitPeriod(-1));
habitNextBtn.addEventListener('click', () => shiftHabitPeriod(1));

// 칸을 누르면 그 날짜의 기록을 적거나 지운다 (지난 날짜도 고칠 수 있다)
habitListEl.addEventListener('click', async (event) => {
  const mark = event.target.closest('button.habit-mark');
  if (!mark) return;
  const { id, day } = mark.dataset;
  const method = mark.dataset.done === 'true' ? 'DELETE' : 'PUT';
  await change(() => api(method, `api/routines/${id}/logs/${day}`));
  const again = habitListEl.querySelector(`button.habit-mark[data-id="${id}"][data-day="${day}"]`);
  if (again) again.focus();
});
