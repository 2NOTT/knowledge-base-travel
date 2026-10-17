export function safeUrl(value) {
  try {
    const url = new URL(String(value).trim().replace(/\s/g, '%20'));
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch { return ''; }
}

export function parseAnswer(value, candidateImages = []) {
  let text = String(value || '');
  const matches = [...text.matchAll(/(?:【图片】|\[图片\]|【参考图片】)/g)];
  let imageBlock = '';
  if (matches.length) {
    const marker = matches.at(-1);
    imageBlock = text.slice(marker.index + marker[0].length);
    text = text.slice(0, marker.index);
  }
  const source = text.match(/(?:【来源】|^#{1,3}\s*(?:参考来源|来源)\s*$)/m);
  let sources = '';
  if (source) {
    sources = text.slice(source.index + source[0].length).trim();
    text = text.slice(0, source.index);
  }
  const markdownImages = [];
  text = text.replace(/!\[[^\]]*\]\((https?:\/\/[^)]+)\)/g, (_, url) => {
    markdownImages.push(url); return '';
  });
  const blockUrls = imageBlock.match(/https?:\/\/[^\s<>"）]+/g) || [];
  const images = [...new Set([
    ...(Array.isArray(candidateImages) ? candidateImages : []),
    ...markdownImages, ...blockUrls,
  ].map(safeUrl).filter(url => url && /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(new URL(url).pathname)))];
  const noReference = /未使用具体|无参考|没有.*(?:来源|参考)|未提供.*(?:来源|参考)/.test(sources);
  return { text: text.trim(), sources, images, noReference };
}

export function progressState(doneList = [], runningList = [], status = 'processing') {
  const done = [...new Set(Array.isArray(doneList) ? doneList.filter(x => typeof x === 'string') : [])];
  const running = [...new Set(Array.isArray(runningList) ? runningList.filter(x => typeof x === 'string') : [])]
    .filter(name => !done.includes(name));
  const terminal = ['completed', 'failed', 'interrupted'].includes(status);
  return {
    done, running, terminal,
    items: [
      ...done.map(name => ({ name, state: 'done' })),
      ...running.map(name => ({ name, state: terminal ? 'unfinished' : 'running' })),
    ],
    label: status === 'failed' ? '本次请求未完成'
      : status === 'interrupted' ? '已停止接收此回答'
      : status === 'completed' ? (running.length ? '回答已生成 · 部分检索未确认完成' : '回答已完成')
      : running.length ? `正在${running.at(-1).replace(/^正在/, '')}…` : '正在准备你的旅行建议…',
  };
}
