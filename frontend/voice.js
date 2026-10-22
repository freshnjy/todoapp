'use strict';

// 음성 입력: 마이크 버튼을 누르고 "장보기에 우유 추가해줘"라고 말하면 저장소의 "장보기" 메모에 들어간다.
// 받아 적는 것은 브라우저의 음성 인식이 하고, 문장을 가르고 넣는 것은 서버가 한다 (docs/api.md의 "음성 입력").
// app.js의 api, refresh, change, render, showNotice, clearNotice, guessCategory와 상태(busy, input)를 쓴다.

const voiceBtn = document.getElementById('voice-btn');
const voicePanel = document.getElementById('voice-panel');
const voiceStatus = document.getElementById('voice-status');
const voiceHeard = document.getElementById('voice-heard');
const voiceBigBtn = document.getElementById('voice-big');
const toastEl = document.getElementById('toast');
const toastText = document.getElementById('toast-text');
const toastAction = document.getElementById('toast-action');
const toastClose = document.getElementById('toast-close');

// "취소"를 보여 주는 시간
const UNDO_MS = 5000;
const VOICE_MESSAGES = {
  denied: '마이크를 쓸 수 없어요. 브라우저의 사이트 설정에서 마이크를 허용해 주세요.',
  silent: '아무 말도 듣지 못했어요. 다시 눌러 말해 주세요.',
  network: '음성 인식에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.',
  failed: '음성을 받아 적지 못했어요. 다시 시도해 주세요.',
  unsupported: '이 브라우저에서는 음성 입력을 쓸 수 없어요. 안드로이드 크롬에서 열어 주세요.',
};

const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
// 바로 듣기 주소(?voice=1)로 열었는지. 홈 화면 아이콘이 이 주소다
const openedForVoice = new URLSearchParams(window.location.search).get('voice') === '1';

let recognition = null;
let listening = false;
// 이번에 받아 적은 글 (확정된 것과 아직 바뀔 수 있는 것)
let heardFinal = '';
let heardInterim = '';
// 사용자가 그만두었는지 (그만두면 넣지 않는다)
let voiceCancelled = false;
// 화면을 열자마자 스스로 듣기 시작한 것인지 (크롬이 막으면 큰 버튼을 보여 준다)
let autoStarted = false;
let voiceError = null;
let toastTimer = null;
let toastHandler = null;

// ---------- 알림 줄 ----------

function hideToast() {
  clearTimeout(toastTimer);
  toastTimer = null;
  toastHandler = null;
  toastEl.hidden = true;
}

// message를 보여 준다. actionLabel이 있으면 버튼을 달고, 누르면 onAction을 부른다.
// duration이 없으면 닫을 때까지 남는다.
function showToast(message, actionLabel, onAction, duration) {
  hideToast();
  toastText.textContent = message;
  toastAction.hidden = !actionLabel;
  toastAction.textContent = actionLabel || '';
  toastHandler = onAction || null;
  toastClose.hidden = Boolean(duration);
  toastEl.hidden = false;
  if (duration) toastTimer = setTimeout(hideToast, duration);
}

toastAction.addEventListener('click', () => {
  const handler = toastHandler;
  hideToast();
  if (handler) handler();
});

toastClose.addEventListener('click', hideToast);

function quoteList(texts) {
  return texts.map((text) => `'${text}'`).join(', ');
}

// 방금 넣은 것을 지운다. undo는 서버에 보낼 지우기 요청 목록을 만든다
async function undoAdded(undo) {
  const undone = await change(async () => {
    for (const path of undo) await api('DELETE', path);
  });
  if (undone) showToast('취소했어요', null, null, 2000);
}

function showAdded(message, undo) {
  showToast(message, '취소', () => undoAdded(undo), UNDO_MS);
}

// 받아 적은 문장을 서버에 보내 넣는다 (docs/api.md의 "음성 입력").
// 메모 제목으로 시작하면 그 메모에, "○○에 △△ 추가해줘"인데 ○○이 메모가 아니면 "제목 없음" 메모에, 그 밖에는 할 일로
async function sendSpoken(text) {
  if (busy) {
    showNotice('저장하는 중이에요. 잠시 뒤 다시 말해 주세요.');
    return;
  }
  const category = guessCategory(text) || 'work';
  let data = null;
  busy = true;
  try {
    data = await api('POST', 'api/voice', { text, category });
    await refresh();
    clearNotice();
  } catch (error) {
    if (!error.unauthorized) showNotice(error.detail || CONNECT_ERROR);
    render();
    return;
  } finally {
    busy = false;
  }
  if (data.result === 'todo') {
    const texts = quoteList(data.todos.map((todo) => todo.text));
    showAdded(`할 일 ${texts} 추가함`, data.todos.map((todo) => `api/todos/${todo.id}`));
    return;
  }
  // 메모에 넣었으면: 방금 넣은 품목을 지운다. 이번에 새로 만든 "제목 없음" 메모면 메모째 지운다
  const memoId = data.memo.id;
  const undo = data.created_memo
    ? [`api/memos/${memoId}`]
    : data.items.map((item) => `api/memos/${memoId}/items/${item.id}`);
  const texts = quoteList(data.items.map((item) => item.text));
  showAdded(`${data.name}에 ${texts} 추가함`, undo);
}

// ---------- 듣기 ----------

function renderVoice() {
  voiceBtn.classList.toggle('is-listening', listening);
  voiceBtn.setAttribute('aria-pressed', String(listening));
  voiceBtn.setAttribute('aria-label', listening ? '듣기 그만두기' : '말로 입력');
  if (listening) {
    voiceStatus.textContent = '듣고 있어요… (예: 장보기에 우유 추가해줘)';
    voiceHeard.textContent = `${heardFinal}${heardInterim}`;
  }
  voicePanel.hidden = !listening && voiceBigBtn.hidden;
}

function showBigButton(message) {
  voiceStatus.textContent = message;
  voiceHeard.textContent = '';
  voiceBigBtn.hidden = false;
  renderVoice();
}

function startListening(isAuto) {
  if (listening || !SpeechRecognitionClass) return;
  heardFinal = '';
  heardInterim = '';
  voiceCancelled = false;
  voiceError = null;
  autoStarted = Boolean(isAuto);
  recognition = new SpeechRecognitionClass();
  recognition.lang = 'ko-KR';
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    heardFinal = '';
    heardInterim = '';
    for (let index = 0; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (result.isFinal) heardFinal += result[0].transcript;
      else heardInterim += result[0].transcript;
    }
    renderVoice();
  };
  recognition.onerror = (event) => {
    voiceError = event.error;
  };
  recognition.onend = () => {
    listening = false;
    recognition = null;
    finishListening();
  };

  try {
    recognition.start();
  } catch (error) {
    recognition = null;
    showNotice(VOICE_MESSAGES.failed);
    return;
  }
  listening = true;
  hideToast();
  clearNotice();
  voiceBigBtn.hidden = true;
  renderVoice();
}

function stopListening() {
  if (!recognition) return;
  voiceCancelled = true;
  recognition.abort();
}

// 듣기가 끝났을 때: 받아 적은 글이 있으면 넣고, 없으면 이유를 알린다
function finishListening() {
  const text = `${heardFinal}${heardInterim}`.trim();
  const wasAuto = autoStarted;
  autoStarted = false;
  renderVoice();
  if (voiceCancelled) return;

  const denied = voiceError === 'not-allowed' || voiceError === 'service-not-allowed';
  if (denied && wasAuto) {
    // 크롬이 터치 없이는 마이크를 켜 주지 않은 경우. 한 번 누르게 한다
    showBigButton('아래 버튼을 누르고 말해 주세요.');
    return;
  }
  if (denied) {
    showNotice(VOICE_MESSAGES.denied);
    return;
  }
  if (voiceError === 'network') {
    showNotice(VOICE_MESSAGES.network);
    return;
  }
  if (text === '') {
    if (wasAuto) showBigButton('아무 말도 듣지 못했어요. 버튼을 누르고 말해 주세요.');
    else showNotice(voiceError && voiceError !== 'no-speech' ? VOICE_MESSAGES.failed : VOICE_MESSAGES.silent);
    return;
  }
  sendSpoken(text);
}

voiceBtn.addEventListener('click', () => {
  if (listening) stopListening();
  else startListening(false);
});

voiceBigBtn.addEventListener('click', () => startListening(false));

// 시작: 음성 인식이 있는 브라우저에서만 마이크 버튼을 보여 준다
if (SpeechRecognitionClass) {
  voiceBtn.hidden = false;
  if (openedForVoice) startListening(true);
} else if (openedForVoice) {
  // 화면을 처음 불러올 때 안내 줄이 지워지므로, 닫을 때까지 남는 알림 줄에 적는다
  showToast(VOICE_MESSAGES.unsupported);
}
