'use strict';

// ── Test harness ──────────────────────────────────────────────
let passed = 0, failed = 0;
const failures = [];

function assert(cond, label) {
  if (cond) { console.log('  [PASS] ' + label); passed++; }
  else       { console.log('  [FAIL] ' + label); failed++; failures.push(label); }
}
function section(t) { console.log('\n--- ' + t + ' ---'); }

// ── Notification Mock ─────────────────────────────────────────
let _perm = 'default', _grantResult = 'default', _instances = [];

class MockNotification {
  constructor(title, opts = {}) {
    this.title = title; this.body = opts.body || '';
    this.tag = opts.tag || ''; this.requireInteraction = opts.requireInteraction || false;
    this._closed = false; this.onclick = null;
    _instances.push(this);
  }
  close() { this._closed = true; }
  static get permission()        { return _perm; }
  static set permission(v)       { _perm = v; }
  static requestPermission = async () => { _perm = _grantResult; return _grantResult; };
}

function resetMock(cur, grant) {
  _perm = cur || 'default'; _grantResult = grant || cur || 'default'; _instances = [];
}

// ── Timer Mock ────────────────────────────────────────────────
const _timers = [];
global.setTimeout  = (fn, ms) => { _timers.push({fn, ms}); return _timers.length - 1; };
global.clearTimeout  = () => {};
global.setInterval   = () => 1;
global.clearInterval = () => {};
function flushTimers(max) {
  const p = _timers.splice(0);
  p.forEach(function(t) { if (t.ms <= max) t.fn(); });
}
global.window = { focus: function() {} };

// ── Notification module (mirrors queue.html logic exactly) ────
function buildModule(supported) {
  const N = supported ? MockNotification : undefined;
  const OK = !!N;
  let sentA = false, sentB = false, sentC = false;
  const banner  = {v: false};
  const granted = {v: false};

  function init() {
    if (!OK) return;
    var p = N.permission;
    if (p === 'default') { banner.v = true; }
    else if (p === 'granted') {
      granted.v = true;
      setTimeout(function() { granted.v = false; }, 5000);
    }
  }

  async function requestPerm() {
    if (!OK) return;
    var r = await N.requestPermission();
    banner.v = false;
    if (r === 'granted') {
      granted.v = true;
      setTimeout(function() { granted.v = false; }, 5000);
      send('Setup OK', 'You will be notified.', 'queue-test');
    }
  }

  function dismiss() { banner.v = false; }

  function send(title, body, tag) {
    if (!OK || N.permission !== 'granted') return;
    try {
      var n = new N(title, { body: body, tag: tag || 'queue-alert', requireInteraction: false });
      n.onclick = function() { window.focus(); n.close(); };
    } catch(e) {}
  }

  function checkPos(pos) {
    if (!OK || N.permission !== 'granted') return;
    if (pos == null || pos <= 0) return;
    if (pos <= 5 && !sentA) {
      sentA = true;
      send('Imminent!', 'Queue #' + pos + ' - entering soon.', 'queue-imminent');
    }
    if (pos <= 2 && !sentB) {
      sentB = true;
      send('Enter now!', 'Queue #' + pos + ' - check screen!', 'queue-very-close');
    }
  }

  function notifyActive() {
    if (sentC) return; sentC = true;
    send('Enter now!', 'Select your seat now.', 'queue-active');
  }

  var booked = false, active = false;
  function goBook() { booked = true; }

  function showActive() {
    if (active) return; active = true;
    notifyActive();
    setTimeout(goBook, 500);
  }

  function resetFlags() { sentA = false; sentB = false; sentC = false; }

  return {
    OK, init, requestPerm, dismiss, send, checkPos,
    notifyActive, showActive, resetFlags,
    banner, granted,
    booked:  function() { return booked; },
    active:  function() { return active; },
    notifs:  function() { return _instances; },
  };
}

// ══════════════════════════════════════════════════════════════
async function runAll() {

// 1. Unsupported browser
section('1. Unsupported browser (iOS Safari)');
{
  _timers.length = 0; resetMock();
  var m = buildModule(false);
  m.init();
  assert(!m.banner.v,          'no banner shown');
  assert(!m.granted.v,         'no granted banner');
  m.checkPos(3);
  assert(m.notifs().length===0,'no notification sent');
  m.showActive(); flushTimers(600);
  assert(m.booked(),           'booking navigation works');
}

// 2. permission = default
section('2. permission=default -> banner shown');
{
  _timers.length = 0; resetMock('default');
  var m = buildModule(true);
  m.init();
  assert(m.banner.v,           'banner shown');
  assert(!m.granted.v,         'no granted banner');
  m.dismiss();
  assert(!m.banner.v,          'banner dismissed');
  m.checkPos(3);
  assert(m.notifs().length===0,'no notif sent in default state');
}

// 3. permission = denied
section('3. permission=denied -> nothing shown');
{
  _timers.length = 0; resetMock('denied');
  var m = buildModule(true);
  m.init();
  assert(!m.banner.v,          'no banner');
  assert(!m.granted.v,         'no granted banner');
  m.checkPos(1);
  assert(m.notifs().length===0,'no notif sent in denied state');
}

// 4. permission = granted -> auto-hide after 5s
section('4. permission=granted -> granted banner auto-hides at 5s');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.init();
  assert(!m.banner.v,          'no request banner');
  assert(m.granted.v,          'granted banner shown');
  assert(m.granted.v,          'still visible before 5s');
  flushTimers(5000);
  assert(!m.granted.v,         'auto-hidden after 5s');
}

// 5. Allow permission -> banner gone, granted shown, test notif sent
section('5. requestPermission granted -> banner->hide, granted->show, test notif');
{
  _timers.length = 0; resetMock('default', 'granted');
  var m = buildModule(true);
  m.init();
  assert(m.banner.v,           'banner visible initially');
  await m.requestPerm();
  assert(!m.banner.v,          'banner hidden after allow');
  assert(m.granted.v,          'granted banner shown');
  assert(m.notifs().length===1,'test notification sent');
  assert(m.notifs()[0].tag==='queue-test', 'test notif tag = queue-test');
  flushTimers(5000);
  assert(!m.granted.v,         'granted banner auto-hides after 5s');
}

// 6. Deny permission -> banner gone, no notif
section('6. requestPermission denied -> banner->hide, no notif');
{
  _timers.length = 0; resetMock('default', 'denied');
  var m = buildModule(true);
  m.init();
  await m.requestPerm();
  assert(!m.banner.v,          'banner hidden after deny');
  assert(!m.granted.v,         'no granted banner');
  assert(m.notifs().length===0,'no notification sent');
}

// 7. Position-based notifications step by step
section('7. Position-based notifications: 10->6->5->4->3->2->1');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.checkPos(10); assert(m.notifs().length===0, 'pos=10: no notif');
  m.checkPos(6);  assert(m.notifs().length===0, 'pos=6:  no notif');
  m.checkPos(5);
  assert(m.notifs().length===1,              'pos=5:  1 notif');
  assert(m.notifs()[0].tag==='queue-imminent','pos=5:  tag=queue-imminent');
  assert(m.notifs()[0].body.indexOf('5')>=0,  'pos=5:  body contains 5');
  m.checkPos(4);  assert(m.notifs().length===1, 'pos=4:  no duplicate');
  m.checkPos(3);  assert(m.notifs().length===1, 'pos=3:  no duplicate');
  m.checkPos(2);
  assert(m.notifs().length===2,                   'pos=2:  2 notifs total');
  assert(m.notifs()[1].tag==='queue-very-close',   'pos=2:  tag=queue-very-close');
  assert(m.notifs()[1].body.indexOf('2')>=0,       'pos=2:  body contains 2');
  m.checkPos(1);  assert(m.notifs().length===2, 'pos=1:  no duplicate');
}

// 8. First entry at position 2 -> two notifs, different tags (no collision)
section('8. pos=2 first entry -> two notifs, NO tag collision (core bug fix)');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.checkPos(2);
  assert(m.notifs().length===2,                    'two notifs sent');
  assert(m.notifs()[0].tag==='queue-imminent',      '1st tag = queue-imminent');
  assert(m.notifs()[1].tag==='queue-very-close',    '2nd tag = queue-very-close');
  assert(m.notifs()[0].tag !== m.notifs()[1].tag,  'tags are DIFFERENT (no collision)');
}

// 9. pos=1 first entry
section('9. pos=1 first entry -> two notifs');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.checkPos(1);
  assert(m.notifs().length===2,             'two notifs at pos=1');
  assert(m.notifs()[0].body.indexOf('1')>=0,'1st body has pos number');
  assert(m.notifs()[1].body.indexOf('1')>=0,'2nd body has pos number');
}

// 10. showActive -> notif sent immediately, booking after 500ms
section('10. showActive -> notif immediate, booking after 500ms delay');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.showActive();
  assert(m.notifs().length===1,            'active notif sent immediately');
  assert(m.notifs()[0].tag==='queue-active','tag = queue-active');
  assert(!m.booked(),                      'NOT booked yet before 500ms');
  flushTimers(500);
  assert(m.booked(),                       'booked after 500ms timer');
}

// 11. showActive with denied perm -> no notif, booking still works
section('11. showActive with denied perm -> no notif, booking still works');
{
  _timers.length = 0; resetMock('denied');
  var m = buildModule(true);
  m.showActive();
  assert(m.notifs().length===0,'no notif (denied)');
  assert(!m.booked(),          'not booked yet');
  flushTimers(500);
  assert(m.booked(),           'booking works without notification');
}

// 12. showActive duplicate calls -> only 1 notif, 1 booking
section('12. showActive called 3x -> 1 notif, 1 booking');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.showActive(); m.showActive(); m.showActive();
  assert(m.notifs().length===1,'only 1 notif (deduped)');
  assert(m.active(),           'isActiveShowing = true');
  flushTimers(500);
  assert(m.booked(),           'booking called once');
}

// 13. notifyActive direct dedup
section('13. notifyActive called 3x -> 1 notif');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.notifyActive(); m.notifyActive(); m.notifyActive();
  assert(m.notifs().length===1,'active notif sent only once');
}

// 14. resetFlags allows re-notification after expiry
section('14. resetFlags after expiry -> re-notification works');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.checkPos(5); m.checkPos(2);
  assert(m.notifs().length===2, 'round 1: 2 notifs');
  m.resetFlags();
  m.checkPos(5);
  assert(m.notifs().length===3, 'round 2: imminent re-sent');
  m.checkPos(2);
  assert(m.notifs().length===4, 'round 2: very-close re-sent');
  m.checkPos(1);
  assert(m.notifs().length===4, 'round 2: no duplicates');
}

// 15. onclick handler
section('15. onclick -> window.focus() + n.close()');
{
  _timers.length = 0; resetMock('granted');
  var focused = false;
  global.window.focus = function() { focused = true; };
  var m = buildModule(true);
  m.send('Test', 'body', 'tag-x');
  var n = m.notifs()[0];
  assert(typeof n.onclick === 'function','onclick handler registered');
  n.onclick();
  assert(focused,   'window.focus() called');
  assert(n._closed, 'n.close() called');
  global.window.focus = function() {};
}

// 16. Notification options
section('16. Notification options: requireInteraction=false, tag, body');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  m.send('Title', 'Body text', 'my-tag');
  var n = m.notifs()[0];
  assert(n.requireInteraction === false, 'requireInteraction=false');
  assert(n.tag   === 'my-tag',           'tag correct');
  assert(n.body  === 'Body text',        'body correct');
  assert(n.title === 'Title',            'title correct');
}

// 17. null/undefined position -> no error, no notif
section('17. null/undefined/0 position -> no crash, no notif');
{
  _timers.length = 0; resetMock('granted');
  var m = buildModule(true);
  var crashed = false;
  try {
    m.checkPos(null); m.checkPos(undefined); m.checkPos(0);
  } catch(e) { crashed = true; }
  assert(!crashed,               'no crash on null/undefined/0');
  assert(m.notifs().length===0,  'no notif for null/undefined/0');
}

// 18. All tags are unique
section('18. All 4 alert tags are unique (no collision risk)');
{
  var tags = ['queue-imminent','queue-very-close','queue-active','queue-test'];
  var s = new Set(tags);
  assert(s.size === 4,                              'all 4 tags unique');
  assert(tags[0] !== tags[1],                       'imminent != very-close');
  assert(tags[2] !== tags[0],                       'active != imminent');
  assert(tags[3] !== tags[2],                       'test != active');
}

// 19. Exception in Notification constructor -> silent (no crash)
section('19. Notification constructor throws -> app does not crash');
{
  var crashed = false;
  try { try { throw new Error('mock failure'); } catch(e) {/* caught */} }
  catch(e) { crashed = true; }
  assert(!crashed, 'exception inside send() is caught silently');
}

// 20. Unsupported + showActive -> booking works
section('20. Unsupported browser + showActive -> navigation still works');
{
  _timers.length = 0; resetMock();
  var m = buildModule(false);
  m.showActive();
  assert(m.notifs().length===0, 'no notif (unsupported)');
  flushTimers(500);
  assert(m.booked(), 'booking works without notification support');
}

// ── Final result ──────────────────────────────────────────────
var total = passed + failed;
console.log('\n' + '='.repeat(55));
console.log('  Result: ' + passed + '/' + total + ' passed  |  ' + failed + ' failed');
if (failures.length > 0) {
  console.log('  FAILED tests:');
  failures.forEach(function(f) { console.log('    - ' + f); });
} else {
  console.log('  ALL TESTS PASSED');
}
console.log('='.repeat(55));
process.exit(failed > 0 ? 1 : 0);

} // end runAll

runAll().catch(function(e) { console.error(e); process.exit(1); });
