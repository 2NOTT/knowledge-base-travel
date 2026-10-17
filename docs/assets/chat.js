import { safeUrl, parseAnswer, progressState } from './chat-state.js';

const $ = id => document.getElementById(id);
const demo = document.body.dataset.demo === 'true' ? await import('./demo.js') : null;
const apiBase = location.origin;
const importBase = `${apiBase}/import-api`;
const storageKey = demo ? 'roam_demo_conversations_v1' : 'roam_conversations_v1';
const sessionIdKey = demo ? 'roam_demo_session_id' : 'kb_session_id';
const newId = () => `sess-${crypto.randomUUID()}`;
const timeLabel = timestamp => new Date(timestamp || Date.now()).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

function readStorage(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}

let sessions = [];
try {
  const saved = JSON.parse(readStorage(storageKey, '[]'));
  sessions = Array.isArray(saved) ? saved.filter(s => typeof s?.id === 'string' && Array.isArray(s.messages)) : [];
} catch { /* A damaged local cache must not prevent opening the app. */ }
const previousSessionId = readStorage(sessionIdKey, '');
let sessionId = previousSessionId || newId();
let activeRequest = null;
let importReady = false;
let toastTimer;
const mobileNavigation = matchMedia('(max-width: 800px)');

function currentSession() {
  let session = sessions.find(s => s.id === sessionId);
  if (!session) {
    session = { id: sessionId, title: '', messages: [] };
    sessions.unshift(session);
  }
  return session;
}

function persist() {
  try {
    localStorage.setItem(sessionIdKey, sessionId);
    localStorage.setItem(storageKey, JSON.stringify(sessions));
  } catch {
    showNotice('浏览器暂时无法保存对话，关闭页面后本地记录可能丢失。');
  }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function toast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4000);
}

function showNotice(message, neutral = false) {
  $('notice').textContent = message;
  $('notice').hidden = !message;
  $('notice').classList.toggle('neutral', neutral);
}

function setSidebar(open) {
  const wasOpen = $('sidebar').classList.contains('open');
  $('sidebar').classList.toggle('open', open);
  $('sidebarScrim').hidden = !open;
  $('menuButton').setAttribute('aria-expanded', String(open));
  $('sidebar').inert = mobileNavigation.matches && !open;
  document.querySelector('.workspace').inert = mobileNavigation.matches && open;
  if (mobileNavigation.matches && !open) $('sidebar').setAttribute('aria-hidden', 'true');
  else $('sidebar').removeAttribute('aria-hidden');
  if (open) $('newChat').focus();
  if (wasOpen && !open) $('menuButton').focus();
}

function showView(view) {
  const importing = view === 'import';
  $('chatView').hidden = importing;
  $('importView').hidden = !importing;
  $('chatActions').hidden = importing;
  $('pageTitle').textContent = importing ? '资料导入' : '旅行问答';
  for (const [id, selected] of [['chatNav', !importing], ['importNav', importing]]) {
    $(id).classList.toggle('active', selected);
    if (selected) $(id).setAttribute('aria-current', 'page');
    else $(id).removeAttribute('aria-current');
  }
  setSidebar(false);
  if (!importing && !currentSession().messages.length) $('chatScroll').scrollTop = 0;
  if (importing) checkImportService();
}

function updateLayout() {
  const hasMessages = $('chat').childElementCount > 0;
  $('welcome').hidden = hasMessages;
  $('inspiration').hidden = hasMessages;
  $('chat').hidden = !hasMessages;
  $('conversationComposerSlot').hidden = !hasMessages;
  $('welcomeComposerSlot').hidden = hasMessages;
  $('chatView').classList.toggle('in-conversation', hasMessages);
  const slot = $(hasMessages ? 'conversationComposerSlot' : 'welcomeComposerSlot');
  if ($('composer').parentElement !== slot) slot.appendChild($('composer'));
  $('btnClear').disabled = !hasMessages || Boolean(activeRequest);
}

function updateSendButton() {
  const busy = Boolean(activeRequest);
  $('send').disabled = busy || !$('input').value.trim();
  $('send').classList.toggle('busy', busy);
  $('composer').setAttribute('aria-busy', String(busy));
  $('streamToggle').disabled = busy;
  $('btnClear').disabled = busy || !$('chat').childElementCount;
  $('composerStatus').textContent = busy ? (demo ? '正在播放预设回答…' : '正在为你整理旅行建议…') : '写下你的旅行想法';
}

function scrollToBottom(force = false) {
  const container = $('chatScroll');
  if (force || container.scrollHeight - container.scrollTop - container.clientHeight < 180) {
    container.scrollTop = container.scrollHeight;
  }
}

function renderRecent() {
  $('recentList').replaceChildren();
  const visible = sessions.filter(s => s.messages.length);
  $('recentEmpty').hidden = Boolean(visible.length);
  for (const session of visible) {
    const button = element('button', `recent-item${session.id === sessionId ? ' active' : ''}`, session.title || '旅行对话');
    button.title = session.title || '旅行对话';
    button.addEventListener('click', () => switchSession(session.id));
    $('recentList').appendChild(button);
  }
}

function appendInline(container, text) {
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|(https?:\/\/[^\s<>"）]+)/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    container.appendChild(document.createTextNode(text.slice(offset, match.index)));
    if (match[1]) container.appendChild(element('strong', '', match[1]));
    else if (match[2]) container.appendChild(element('code', '', match[2]));
    else {
      const label = match[3] || match[5];
      const url = safeUrl(match[4] || match[5]);
      if (url) {
        const link = element('a', '', label);
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        container.appendChild(link);
      } else container.appendChild(document.createTextNode(label));
    }
    offset = match.index + match[0].length;
  }
  container.appendChild(document.createTextNode(text.slice(offset)));
}

function renderBody(container, text) {
  container.replaceChildren();
  let list = null;
  for (const block of text.split(/\n\s*\n/)) {
    for (const line of block.split('\n')) {
      if (!line.trim()) continue;
      const heading = line.match(/^#{1,6}\s+(.+)/);
      const item = line.match(/^\s*(?:[-*]\s+|(\d+)[.、]\s*)(.+)/);
      if (item) {
        const type = item[1] ? 'OL' : 'UL';
        if (!list || list.tagName !== type) { list = element(type.toLowerCase()); container.appendChild(list); }
        const li = element('li'); appendInline(li, item[2]); list.appendChild(li);
      } else {
        list = null;
        const paragraph = element(heading ? 'h3' : 'p');
        appendInline(paragraph, heading ? heading[1] : line);
        container.appendChild(paragraph);
      }
    }
    list = null;
  }
}

function renderProgress(reply, status = 'processing') {
  const state = progressState(reply.done, reply.running, status);
  reply.progress.querySelector('summary').textContent = state.label;
  const list = reply.progress.querySelector('ul');
  list.replaceChildren();
  for (const item of state.items) {
    list.appendChild(element('li', item.state, item.name + (item.state === 'unfinished' ? ' · 未确认完成' : '')));
  }
  reply.progress.hidden = !state.items.length;
  if (state.terminal) reply.progress.open = false;
  reply.pending.textContent = state.label;
  return state;
}

function createUserMessage(text) {
  const row = element('article', 'message user');
  row.setAttribute('aria-label', '你的问题');
  row.appendChild(element('div', 'user-bubble', text));
  $('chat').appendChild(row);
}

function createReply() {
  const row = element('article', 'message assistant');
  row.setAttribute('aria-label', '行知的回答');
  const heading = element('div', 'assistant-heading');
  heading.append(element('span', 'assistant-mark', '行'), element('span', '', '行知 · 旅行助手'));
  const pending = element('div', 'answer-pending', demo ? '正在打开演示案例…' : '正在准备你的旅行建议…');
  const body = element('div', 'answer');
  const progress = element('details', 'progress');
  progress.append(element('summary', '', '正在准备你的旅行建议…'), element('ul'));
  progress.hidden = true;
  row.append(heading, pending, body, progress);
  $('chat').appendChild(row);
  return { row, body, pending, progress, done: [], running: [], raw: '', settled: false };
}

function renderCompleted(reply, record) {
  reply.pending.hidden = true;
  reply.body.classList.remove('streaming');
  reply.done = record.done || reply.done;
  reply.running = record.running || reply.running;
  const parsed = parseAnswer(record.text, record.image_urls);
  if (parsed.text) renderBody(reply.body, parsed.text);
  for (const imageUrl of parsed.images) {
    let gallery = reply.body.querySelector('.answer-images');
    if (!gallery) { gallery = element('div', 'answer-images'); reply.body.appendChild(gallery); }
    const link = element('a'); link.href = imageUrl; link.target = '_blank'; link.rel = 'noopener noreferrer';
    const image = element('img'); image.src = imageUrl; image.alt = '回答中的参考图片'; image.loading = 'lazy'; image.referrerPolicy = 'no-referrer';
    image.addEventListener('error', () => { link.replaceChildren(element('span', '', '图片暂时无法加载，点击查看原图')); });
    link.appendChild(image); gallery.appendChild(link);
  }
  const status = record.error ? (record.interrupted ? 'interrupted' : 'failed') : 'completed';
  const state = renderProgress(reply, status);
  if (record.error) {
    const box = element('div', 'reply-error');
    box.appendChild(element('p', '', record.interrupted ? '已停止接收上一个回答。后台任务可能仍在运行。' : '暂时没能完成这次回答，请稍后重试。'));
    const details = element('details', 'error-details');
    details.append(element('summary', '', '查看具体原因'), element('pre', '', record.error));
    box.appendChild(details); reply.row.insertBefore(box, reply.progress);
  } else if (state.running.length || parsed.noReference) {
    const message = state.running.length
      ? '部分检索未确认完成，本次回答可能不包含完整的知识库资料。'
      : '本次回答未引用具体资料，请结合官方信息核实。';
    reply.row.insertBefore(element('div', 'reply-warning', message), reply.progress);
  }
  if (parsed.sources) {
    const details = element('details', 'source-details');
    details.appendChild(element('summary', '', parsed.noReference ? '来源说明 · 未引用具体资料' : '查看回答来源'));
    const sourceContent = element('div', 'source-content'); appendInline(sourceContent, parsed.sources);
    details.appendChild(sourceContent); reply.row.appendChild(details);
  }
  const footer = element('div', 'reply-footer');
  footer.appendChild(element('span', '', `${demo ? '预设示例 · ' : ''}${timeLabel(record.ts)} · ${state.label}`));
  if (record.text) {
    const copy = element('button', 'copy-answer', '复制回答');
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(record.text); toast('回答已复制'); }
      catch { toast('无法访问剪贴板，请选择回答文字后复制。'); }
    });
    footer.appendChild(copy);
  }
  reply.row.appendChild(footer);
}

function renderConversation() {
  $('chat').replaceChildren();
  for (const record of currentSession().messages) {
    if (record.role === 'user') createUserMessage(String(record.text || ''));
    else if (record.role === 'assistant') renderCompleted(createReply(), record);
  }
  renderRecent(); updateLayout(); updateSendButton();
  if (currentSession().messages.length) scrollToBottom(true);
  else $('chatScroll').scrollTop = 0;
}

function releaseRequest(request) {
  request.stream?.close();
  clearTimeout(request.timeout);
  clearTimeout(request.finalTimer);
  if (activeRequest === request) { activeRequest = null; updateSendButton(); }
}

function finish(request, data = {}) {
  if (request.reply.settled) return;
  request.reply.settled = true;
  const reply = request.reply;
  const text = data.answer || reply.raw;
  const error = data.error || (!text ? '服务未返回有效回答，请重试。' : '');
  const record = { role: 'assistant', text, image_urls: data.image_urls || [], error, interrupted: data.interrupted || false, done: reply.done, running: reply.running, ts: Date.now() };
  renderCompleted(reply, record);
  request.session.messages.push(record);
  releaseRequest(request); persist(); renderRecent(); scrollToBottom();
}

function interruptRequest() {
  if (!activeRequest) return;
  const request = activeRequest;
  finish(request, { answer: request.reply.raw, error: '用户切换了对话，已断开原回答的接收。', interrupted: true });
  request.controller.abort();
}

function switchSession(id) {
  interruptRequest(); sessionId = id; persist();
  showNotice(''); showView('chat'); renderConversation(); loadHistory();
}

async function loadHistory() {
  if (demo) return;
  const session = currentSession();
  const initialLength = session.messages.length;
  try {
    const response = await fetch(`${apiBase}/history/${encodeURIComponent(session.id)}`, { signal: AbortSignal.timeout(6000) });
    if (!response.ok) throw new Error('history unavailable');
    const data = await response.json();
    if (sessionId !== session.id || activeRequest || session.messages.length !== initialLength) return;
    if (Array.isArray(data.items) && data.items.length) {
      session.messages = data.items.filter(item => ['user', 'assistant'].includes(item.role)).map(item => ({ ...item, ts: Number(item.ts) * 1000 }));
      session.title = session.messages.find(item => item.role === 'user')?.text?.slice(0, 28) || '旅行对话';
      persist(); renderConversation();
    }
  } catch {
    if (sessionId === session.id && session.messages.length) showNotice('历史服务暂时不可用，已显示此浏览器保存的对话。', true);
  }
}

async function onSend(event) {
  event.preventDefault();
  const text = $('input').value.trim();
  if (!text || activeRequest) return;
  showNotice('');
  const session = currentSession();
  session.title ||= text.slice(0, 28);
  session.messages.push({ role: 'user', text, ts: Date.now() });
  $('input').value = ''; $('input').style.height = '';
  createUserMessage(text);
  const reply = createReply();
  const request = { reply, session, controller: new AbortController(), stream: null };
  activeRequest = request;
  updateLayout(); updateSendButton(); renderRecent(); persist(); scrollToBottom(true);
  if (demo) {
    const example = demo.findDemoExample(text, session.messages.slice(0, -1));
    const answer = example?.answer || '这里是公开作品演示，暂不提供自由问答。可以试试成都住宿、杭州两日游、云南古城路线，或点击首页的旅行卡片。\n\n【来源】\n本次未使用具体资料；以上为演示范围说明。';
    if ($('streamToggle').checked && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      for (let end = 0; end < answer.length; end += 20) {
        await new Promise(resolve => setTimeout(resolve, 35));
        if (reply.settled) return;
        reply.raw = answer.slice(0, end + 20);
        reply.pending.hidden = true;
        reply.body.classList.add('streaming');
        reply.body.textContent = parseAnswer(reply.raw).text;
        scrollToBottom();
      }
    }
    finish(request, { answer });
    return;
  }
  const resetWaitTimer = () => {
    clearTimeout(request.timeout);
    request.timeout = setTimeout(() => {
      finish(request, { error: '超过两分钟未收到新的回答或进度。检索服务可能不可用，可以新建对话后重试。' });
      request.controller.abort();
    }, 120000);
  };
  resetWaitTimer();
  try {
    const streaming = $('streamToggle').checked;
    const response = await fetch(`${apiBase}/query`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: request.controller.signal,
      body: JSON.stringify({ query: text, session_id: session.id, is_stream: streaming }),
    });
    if (!response.ok) throw new Error(`问答服务返回 ${response.status}，请稍后重试。`);
    const data = await response.json();
    if (reply.settled) return;
    if (!streaming) {
      reply.done = data.done_list || []; finish(request, data); return;
    }
    if (!data.session_id || data.session_id !== session.id) throw new Error('会话标识不匹配，已停止接收。请新建对话重试。');
    const stream = new EventSource(`${apiBase}/stream/${encodeURIComponent(data.session_id)}`);
    request.stream = stream;
    stream.addEventListener('progress', event => {
      if (reply.settled) return;
      resetWaitTimer();
      try {
        const progress = JSON.parse(event.data);
        reply.done = progress.done_list || [];
        reply.running = progress.running_list || [];
        renderProgress(reply, progress.status);
        if (progress.status === 'failed') finish(request, { error: progress.error || '检索或生成过程未完成。请稍后重试。' });
        // The final payload may arrive just after the terminal progress event.
        if (progress.status === 'completed' && !request.finalTimer) request.finalTimer = setTimeout(() => finish(request), 1500);
      } catch { finish(request, { error: '收到无法解析的进度数据，请重试。' }); }
    });
    stream.addEventListener('delta', event => {
      if (reply.settled) return;
      resetWaitTimer();
      try {
        reply.raw += JSON.parse(event.data).delta || '';
        reply.pending.hidden = true;
        reply.body.classList.add('streaming');
        reply.body.textContent = parseAnswer(reply.raw).text;
        scrollToBottom();
      } catch { finish(request, { error: '收到无法解析的回答数据，请重试。' }); }
    });
    for (const name of ['final', 'final_answer']) stream.addEventListener(name, event => {
      try { finish(request, JSON.parse(event.data)); }
      catch { finish(request, { error: '无法读取最终回答，请重试。' }); }
    });
    stream.addEventListener('error', event => {
      let message = '回答连接已中断，请稍后重试。';
      try { if (event.data) message = JSON.parse(event.data).error || message; } catch { /* Keep the connection error message. */ }
      finish(request, { answer: reply.raw, error: message });
    });
  } catch (error) {
    if (!reply.settled) finish(request, { error: error.message || '无法连接问答服务。' });
  }
}

async function checkHealth() {
  if (demo) {
    $('connectionStatus').className = 'connection-status connected';
    $('connectionText').textContent = '交互演示 · 预设案例';
    $('connectionStatus').title = '公开站使用预设回答，不连接模型或数据库。';
    return;
  }
  let connected = false;
  try { connected = (await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(3500) })).ok; } catch { /* Show offline status. */ }
  $('connectionStatus').className = `connection-status ${connected ? 'connected' : 'offline'}`;
  $('connectionText').textContent = connected ? '问答服务已连接' : '问答服务未连接';
}

async function checkImportService() {
  if (demo) {
    $('importServiceStatus').textContent = '公开站仅展示导入流程，不上传文件。完整 Markdown / PDF 导入功能可在本地运行源码体验。';
    return;
  }
  try { importReady = (await fetch(`${importBase}/health`, { signal: AbortSignal.timeout(2500) })).ok; }
  catch { importReady = false; }
  $('importServiceStatus').textContent = importReady
    ? '导入服务已连接。请确认知识库服务可用后再上传资料。'
    : '导入服务暂未连接，当前无法上传。请先恢复导入服务及其依赖的知识库服务。';
  $('importServiceStatus').classList.toggle('ready', importReady);
  $('fileInput').disabled = !importReady;
  $('dropZone').classList.toggle('unavailable', !importReady);
  $('dropZone').setAttribute('aria-disabled', String(!importReady));
}

async function uploadFile(file) {
  const row = element('article', 'upload-item');
  const info = element('div', 'upload-item-info');
  info.append(element('strong', '', file.name), element('small', '', `${(file.size / 1024).toFixed(1)} KB`));
  const detail = element('div', 'upload-detail', '正在上传资料…');
  info.appendChild(detail);
  const status = element('span', 'upload-status', '上传中');
  row.append(info, status); $('fileList').prepend(row);
  try {
    const form = new FormData(); form.append('files', file);
    const response = await fetch(`${importBase}/upload`, { method: 'POST', body: form, signal: AbortSignal.timeout(120000) });
    if (!response.ok) throw new Error(`上传失败（${response.status}），请检查导入服务。`);
    const data = await response.json();
    const taskId = data.task_ids?.[0];
    if (!taskId) throw new Error('服务未返回导入任务编号。');
    status.textContent = '导入中';
    detail.textContent = '资料已上传，等待处理进度…';
    let consecutiveErrors = 0;
    const poll = async () => {
      try {
        const result = await fetch(`${importBase}/status/${encodeURIComponent(taskId)}`, { signal: AbortSignal.timeout(10000) });
        if (!result.ok) throw new Error('进度服务暂不可用');
        const progress = await result.json(); consecutiveErrors = 0;
        const done = Array.isArray(progress.done_list) ? progress.done_list : [];
        const running = Array.isArray(progress.running_list) ? progress.running_list : [];
        detail.textContent = `已完成 ${done.length} 个步骤${running.length ? ` · 正在${running.join('、')}` : ''}`;
        if (progress.status === 'completed') { row.classList.add('completed'); status.textContent = '导入完成'; return; }
        if (progress.status === 'failed') { row.classList.add('failed'); status.textContent = '导入失败'; detail.textContent = progress.error || '处理未完成，请检查服务后重试。'; return; }
      } catch {
        consecutiveErrors++;
        detail.textContent = '暂时无法获取进度，正在重新连接…';
        if (consecutiveErrors >= 3) { status.textContent = '进度未知'; detail.textContent = `无法连接进度服务，后台任务可能仍在执行。任务编号：${taskId}`; return; }
      }
      setTimeout(poll, 2000);
    };
    poll();
  } catch (error) { row.classList.add('failed'); status.textContent = '上传失败'; detail.textContent = error.message; }
}

function handleFiles(files) {
  if (!importReady) { toast('导入服务尚未连接，暂时不能上传。'); return; }
  for (const file of files) {
    if (!/\.(md|pdf)$/i.test(file.name)) { toast(`「${file.name}」不是支持的 PDF 或 Markdown 文件。`); continue; }
    uploadFile(file);
  }
}

$('composer').addEventListener('submit', onSend);
$('input').addEventListener('input', () => {
  updateSendButton(); $('input').style.height = 'auto';
  $('input').style.height = `${Math.min($('input').scrollHeight, 210)}px`;
});
$('input').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault(); $('composer').requestSubmit();
  }
});
for (const button of document.querySelectorAll('[data-prompt]')) button.addEventListener('click', () => {
  $('input').value = button.dataset.prompt; updateSendButton(); $('input').focus();
});
$('newChat').addEventListener('click', () => {
  interruptRequest(); sessionId = newId(); currentSession(); persist();
  showNotice(''); showView('chat'); renderConversation(); $('input').value = ''; updateSendButton(); $('input').focus();
});
$('chatNav').addEventListener('click', () => showView('chat'));
$('importNav').addEventListener('click', () => showView('import'));
$('menuButton').addEventListener('click', () => setSidebar(!$('sidebar').classList.contains('open')));
$('sidebarScrim').addEventListener('click', () => setSidebar(false));
document.addEventListener('keydown', event => { if (event.key === 'Escape') setSidebar(false); });
mobileNavigation.addEventListener('change', () => setSidebar(false));
$('connectionStatus').addEventListener('click', () => { toast(demo ? '此站使用预设案例，回答在浏览器播放，对话只保存在此浏览器。' : '连接状态仅代表问答服务在线；知识库检索、历史记录和资料导入依赖各自的后台服务。'); checkHealth(); });
$('btnClear').addEventListener('click', () => { $('clearError').hidden = true; $('clearDialog').showModal(); });
$('confirmClear').addEventListener('click', async () => {
  $('confirmClear').disabled = true;
  try {
    if (!demo) {
      const response = await fetch(`${apiBase}/history/${encodeURIComponent(sessionId)}`, { method: 'DELETE', signal: AbortSignal.timeout(6000) });
      if (!response.ok) throw new Error('服务端暂时无法清空历史，当前对话已保留。请稍后重试。');
    }
    currentSession().messages = []; currentSession().title = '';
    persist(); renderConversation(); $('clearDialog').close(); showNotice(''); toast('当前对话已清空');
  } catch (error) { $('clearError').textContent = error.message; $('clearError').hidden = false; }
  finally { $('confirmClear').disabled = false; }
});
$('fileInput').addEventListener('change', event => { handleFiles(event.target.files); event.target.value = ''; });
$('dropZone').addEventListener('keydown', event => {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (importReady) $('fileInput').click(); else toast('导入服务尚未连接。'); }
});
$('dropZone').addEventListener('dragover', event => { event.preventDefault(); if (importReady) $('dropZone').classList.add('dragover'); });
$('dropZone').addEventListener('dragleave', () => $('dropZone').classList.remove('dragover'));
$('dropZone').addEventListener('drop', event => { event.preventDefault(); $('dropZone').classList.remove('dragover'); handleFiles(event.dataTransfer.files); });

if (demo) {
  const banner = element('div', 'demo-banner');
  banner.append(element('strong', '', '作品交互演示'), element('span', '', '预设问答 · 无需登录 · 不上传文件'));
  const source = element('a', '', '查看项目源码 ↗');
  source.href = 'https://github.com/2NOTT/knowledge-base-travel#readme';
  source.target = '_blank'; source.rel = 'noopener noreferrer';
  banner.appendChild(source);
  document.querySelector('.topbar').after(banner);
  document.querySelector('.page-title > span').textContent = '旅游 RAG · 项目作品';
  document.querySelector('.welcome-description').textContent = '从成都、杭州或云南开始，体验有来源的旅行问答。此站播放预设案例，完整 AI 服务见源码。';
  const facts = element('p', 'demo-facts', '本地已验证：30 份课程资料 · 1,153 个切片 · 多路检索与来源追溯');
  $('welcome').appendChild(facts);
  $('clearDialog').querySelector('h2 + p').textContent = '仅删除当前浏览器中的这段演示对话，其他对话不会受到影响。';
  $('dropZone').classList.add('unavailable');
  $('dropZone').setAttribute('aria-disabled', 'true');
  $('dropZone').tabIndex = -1;
  $('dropZone').querySelector('strong').textContent = '公开演示不接收文件';
  $('dropZone').querySelector('small').textContent = '完整应用支持 Markdown 和 PDF，下面展示真实处理流程的说明。';
  const steps = element('ol', 'demo-import-steps');
  for (const [title, detail] of [
    ['读取资料', 'Markdown 直接读取；PDF 通过 MinerU 解析为 Markdown。'],
    ['提取旅游元数据', '保留目的地、主题、文件名与章节，让回答可以追溯来源。'],
    ['切分与向量入库', '按章节切分，生成 BGE-M3 稠密与稀疏向量，写入 Milvus。'],
    ['保存原文件', 'MinIO 保存资料；问答时进行混合召回、融合、重排和回答。'],
  ]) {
    const step = element('li');
    step.append(element('strong', '', title), element('p', '', detail));
    steps.appendChild(step);
  }
  $('fileList').appendChild(steps);
}
currentSession(); persist(); renderConversation(); setSidebar(false); checkHealth();
if (!demo) setInterval(checkHealth, 30000);
if (previousSessionId) loadHistory();
