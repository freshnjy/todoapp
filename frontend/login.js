'use strict';

// 로그인 화면. 주소는 상대 경로로 쓴다 (nginx가 /todo/ 접두사를 뗀다).
const loginForm = document.getElementById('login-form');
const passwordInput = document.getElementById('password');
const loginError = document.getElementById('login-error');
const loginButton = document.getElementById('login-button');

function goHome() {
  window.location.replace('./');
}

function messageFor(response) {
  if (response.status === 401) return '비밀번호가 맞지 않습니다.';
  if (response.status === 429) {
    const seconds = Number(response.headers.get('Retry-After'));
    return seconds > 0
      ? `여러 번 틀려서 잠시 막혔어요. ${seconds}초 뒤에 다시 시도해 주세요.`
      : '여러 번 틀려서 잠시 막혔어요. 잠시 후 다시 시도해 주세요.';
  }
  if (response.status === 503) return '서버에 로그인 설정이 없습니다.';
  return '로그인하지 못했어요. 잠시 후 다시 시도해 주세요.';
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const password = passwordInput.value;
  if (password === '') {
    passwordInput.focus();
    return;
  }
  loginButton.disabled = true;
  loginError.textContent = '';
  try {
    const response = await fetch('api/session', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (response.ok) {
      goHome();
      return;
    }
    loginError.textContent = messageFor(response);
    passwordInput.select();
  } catch (error) {
    loginError.textContent = '서버와 연결하지 못했어요. 잠시 후 다시 시도해 주세요.';
  } finally {
    loginButton.disabled = false;
  }
});

// 이미 로그인한 기기라면 바로 할 일 화면으로 간다
fetch('api/session', { credentials: 'same-origin' })
  .then((response) => (response.ok ? response.json() : null))
  .then((data) => {
    if (data && data.authenticated) goHome();
  })
  .catch(() => {});
