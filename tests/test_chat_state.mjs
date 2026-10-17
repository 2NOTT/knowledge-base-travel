import { test } from 'node:test';
import assert from 'node:assert/strict';
import { safeUrl, parseAnswer, progressState } from '../web/assets/chat-state.js';
import { demoExamples, findDemoExample } from '../web/assets/demo.js';

test('demo selects supported topics and preserves city context for follow-ups', () => {
  assert.equal(findDemoExample('第一次去成都，住在哪个区域比较方便？').topic, 'stay');
  assert.equal(findDemoExample('从成都机场到市中心有哪些交通方式？').topic, 'transport');
  assert.equal(findDemoExample('想看云南大理丽江怎么安排行程').city, '云南');
  assert.equal(findDemoExample('继续玩两天', [{ role: 'user', text: '去杭州玩' }]).city, '杭州');
  assert.ok(demoExamples.every(example => parseAnswer(example.answer).sources));
});

test('demo never presents an unrelated preset as an answer to unsupported questions', () => {
  assert.equal(findDemoExample('帮我写 Python'), null);
  assert.equal(findDemoExample('杭州住哪家酒店'), null);
  assert.equal(findDemoExample('杭州天气怎么样'), null);
});

test('terminal answers never leave unresolved retrievals spinning', () => {
  const result = progressState(['网络搜索', '生成答案'], ['切片搜索', '切片搜索(假设性文档)'], 'completed');
  assert.equal(result.terminal, true);
  assert.ok(result.items.every(item => item.state !== 'running'));
  assert.equal(result.items.filter(item => item.state === 'unfinished').length, 2);
  assert.match(result.label, /未确认完成/);
  assert.equal(progressState(['搜索'], ['搜索'], 'completed').running.length, 0);
});

test('answer sources and safe images survive legacy payloads without allowing script URLs', () => {
  const result = parseAnswer('**成都**可以慢慢逛。\n【来源】\n- 本次回答未使用具体文件作为参考。\n【图片】\nhttps://example.com/a.png', ['javascript:alert(1)', 'https://example.com/a.png']);
  assert.equal(result.text, '**成都**可以慢慢逛。');
  assert.equal(result.noReference, true);
  assert.deepEqual(result.images, ['https://example.com/a.png']);
  assert.equal(safeUrl('javascript:alert(1)'), '');
  assert.equal(safeUrl('data:text/html,<script>alert(1)</script>'), '');
  assert.equal(safeUrl('file:///C:/secret.png'), '');
  assert.equal(safeUrl('https://example.com/a b.png'), 'https://example.com/a%20b.png');
  assert.equal(progressState(null, null, 'failed').terminal, true);
});
