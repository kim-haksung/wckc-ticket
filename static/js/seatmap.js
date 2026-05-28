/**
 * 좌석 배치도 렌더링 모듈
 * 선교 70주년 기념관 대강당 - 실제 배치도(PDF) 기반
 *
 * 1층: 가(좌외)/나(좌내)/다(우내)/라(우외) - 부채꼴 형태
 * 2층: 마(좌발코니)/사/아/자/차/카/타/바(우발코니)
 */

const SeatMap = (() => {
  const S      = 13;   // 좌석 크기(px)
  const G      = 2;    // 좌석 간격(px)
  const STEP   = S + G;
  const AISLE  = 20;   // 구역 간 통로
  const DIS_GAP  = 5;   // 장애인 행과 번호 좌석 행 사이 간격(px)
  const AISLE_H  = 14;  // 1층 가로 복도 높이(px)

  // 장애인 행 전체 높이 = S(아이콘 높이) + DIS_GAP
  function disHeight(sec) {
    const cfg = sections[sec];
    return (cfg && cfg.disability_cols > 0) ? (S + DIS_GAP) : 0;
  }
  // 복도 오프셋: 해당 행(1-based)이 복도 이후 행이면 AISLE_H 반환
  function aisleOffset(sec, row1based) {
    const cfg = sections[sec];
    return (cfg && cfg.aisle_after_row > 0 && row1based > cfg.aisle_after_row)
           ? AISLE_H : 0;
  }

  const svgNS = 'http://www.w3.org/2000/svg';

  let seats        = {};   // { id: { section, row, col, seat_no, status } }
  let sections     = {};   // { sec: { label, rows, row_seats, align } }
  let selected     = [];
  let currentFloor = 1;
  let currentSvgId = 'seatMapSvg';
  let onSelectChange = null;
  let onLoadCallback = null;
  const MAX_SEATS    = 10;  // 1인 최대 예매 가능 총 좌석 수
  let reservedCount  = 0;   // 서버에서 받아온 기존 확정 예매 수
  let effectiveMax   = 10;  // 이번 세션에서 추가 선택 가능한 좌석 수

  // ── 큐 토큰 (booking.html 에서 setToken으로 주입) ───────────
  let queueToken = '';
  let seatPollTimer = null;

  // ── 층별 티켓 금액 (booking.html 에서 setPrices로 주입, 기본 10,000원) ──
  let _floorPrices = { 1: 10000, 2: 10000 };

  // ── 관리자 모드 (admin/seats.html 에서 setAdminMode(true)로 활성화) ──
  let adminMode = false;

  // ── 유틸 ──────────────────────────────────────
  function makeSvgEl(tag, attrs) {
    const el = document.createElementNS(svgNS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    return el;
  }

  function maxCols(sec) {
    const cfg = sections[sec];
    if (!cfg) return 0;
    return Math.max(...cfg.row_seats);
  }
  function secWidth(sec)  { return maxCols(sec) * STEP; }
  function secHeight(sec) {
    const cfg = sections[sec];
    if (!cfg) return 0;
    // 복도가 있는 구역은 AISLE_H 만큼 추가
    const ah = cfg.aisle_after_row > 0 ? AISLE_H : 0;
    return cfg.rows * STEP + ah;
  }

  // ── 구역 렌더링 ─────────────────────────────────
  /**
   * @param {string} sec        구역 코드
   * @param {number} offsetX    SVG 내 X 시작 위치
   * @param {number} offsetY    SVG 내 Y 시작 위치
   * @param {string} [align]    'left' | 'center' | 'right'  (row 정렬)
   *
   * 구역 레이아웃 (Y축):
   *   offsetY + 0            ← 장애인 행 시작 (disability_cols > 0 인 구역만)
   *   offsetY + S + DIS_GAP  ← 번호 좌석 row 1 시작
   */
  function buildSection(sec, offsetX, offsetY, align) {
    const cfg = sections[sec];
    if (!cfg) return null;

    align = align || cfg.align || 'center';

    const sw      = secWidth(sec);
    const sh      = secHeight(sec);
    const disH    = disHeight(sec);          // 장애인 행 높이 (없으면 0)
    const totalH  = disH + sh;               // 배경박스 전체 높이
    const seatY0  = offsetY + disH;          // 번호 좌석 시작 Y

    const g = makeSvgEl('g', { 'data-sec': sec });

    // ── 배경 박스 (장애인 행 포함한 전체 높이) ──
    const bg = makeSvgEl('rect', {
      x: offsetX - 2, y: offsetY - 2,
      width: sw + 4, height: totalH + 4,
      rx: 6, fill: '#EBF3FB', stroke: '#B0CCE1', 'stroke-width': 1
    });
    g.appendChild(bg);

    // ── 구역 레이블 ──
    const lbl = makeSvgEl('text', {
      x: offsetX + sw / 2, y: offsetY - 8,
      'text-anchor': 'middle',
      'font-size': 11, 'font-weight': 'bold',
      fill: '#145285', 'font-family': 'Malgun Gothic,sans-serif'
    });
    lbl.textContent = cfg.label;
    g.appendChild(lbl);

    // ── 장애인 행 렌더링 ──────────────────────────
    const disCols = cfg.disability_cols || 0;
    if (disCols > 0) {
      // 장애인 행도 번호 좌석 행과 동일한 정렬 기준 적용
      let disOffset;
      if (align === 'right')       disOffset = (maxCols(sec) - disCols) * STEP;
      else if (align === 'left')   disOffset = 0;
      else                         disOffset = ((maxCols(sec) - disCols) / 2) * STEP;

      for (let i = 0; i < disCols; i++) {
        const dx = offsetX + disOffset + i * STEP;
        const dy = offsetY;

        // 장애인석 박스
        const dr = makeSvgEl('rect', {
          x: dx, y: dy, width: S, height: S, rx: 2,
          class: 'seat-disability'
        });
        g.appendChild(dr);

        // 휠체어 아이콘 (♿)
        const dt = makeSvgEl('text', {
          x: dx + S / 2, y: dy + S - 2,
          'text-anchor': 'middle',
          'dominant-baseline': 'auto',
          'font-size': 9,
          fill: '#5a7fa6',
          'font-family': 'Malgun Gothic,sans-serif',
          'pointer-events': 'none'
        });
        dt.textContent = '♿';
        g.appendChild(dt);
      }
    }

    // ── 번호 좌석 그리기 ─────────────────────────
    const sectionSeats = Object.entries(seats).filter(([, v]) => v.section === sec);
    sectionSeats.forEach(([id, info]) => {
      const r        = info.row - 1;
      const c        = info.col - 1;
      const rowCount = cfg.row_seats[r] || 1;

      // align에 따른 행 오프셋 계산 (부채꼴 효과)
      let rowOffset;
      if (align === 'right') {
        rowOffset = (maxCols(sec) - rowCount) * STEP;
      } else if (align === 'left') {
        rowOffset = 0;
      } else {
        rowOffset = ((maxCols(sec) - rowCount) / 2) * STEP;
      }

      const sx = offsetX + rowOffset + c * STEP;
      const sy = seatY0 + r * STEP + aisleOffset(sec, info.row);  // 복도 이후 행은 AISLE_H 추가

      const rect = makeSvgEl('rect', {
        x: sx, y: sy,
        width: S, height: S, rx: 2,
        'data-id':  id,
        'data-sec': sec,
        'data-row': info.row,
        'data-col': info.col,
        'data-no':  info.seat_no,
        class: `seat-rect ${info.status}${adminMode && info.status === 'blocked' ? ' admin-blocked' : ''}`
      });
      g.appendChild(rect);

      // 차단 좌석에 × 표시 (사용자/관리자 모드 공통)
      if (info.status === 'blocked') {
        const xMark = makeSvgEl('text', {
          x: sx + S / 2, y: sy + S - 2,
          'text-anchor': 'middle',
          'font-size': 10, 'font-weight': 'bold',
          fill: adminMode ? '#7f1d1d' : '#ffffff',
          'font-family': 'Malgun Gothic,sans-serif',
          'pointer-events': 'none'
        });
        xMark.textContent = '×';
        g.appendChild(xMark);
      }
    });

    return g;
  }

  /** 마/바 구역: 세로로 긴 발코니 */
  function buildBalcony(sec, offsetX, offsetY) {
    const cfg = sections[sec];
    if (!cfg) return null;

    const sw = secWidth(sec);
    const sh = secHeight(sec);

    const g = makeSvgEl('g', { 'data-sec': sec });

    const bg = makeSvgEl('rect', {
      x: offsetX - 2, y: offsetY - 2,
      width: sw + 4, height: sh + 4,
      rx: 6, fill: '#FFF3E0', stroke: '#FFB74D', 'stroke-width': 1.5
    });
    g.appendChild(bg);

    const lbl = makeSvgEl('text', {
      x: offsetX + sw / 2, y: offsetY - 8,
      'text-anchor': 'middle',
      'font-size': 10, 'font-weight': 'bold',
      fill: '#E65100', 'font-family': 'Malgun Gothic,sans-serif'
    });
    lbl.textContent = cfg.label;
    g.appendChild(lbl);

    const sectionSeats = Object.entries(seats).filter(([, v]) => v.section === sec);
    sectionSeats.forEach(([id, info]) => {
      const r = info.row - 1;
      const c = info.col - 1;
      const sx = offsetX + c * STEP;
      const sy = offsetY + r * STEP;

      const rect = makeSvgEl('rect', {
        x: sx, y: sy,
        width: S, height: S, rx: 2,
        'data-id':  id,
        'data-sec': sec,
        'data-row': info.row,
        'data-col': info.col,
        'data-no':  info.seat_no,
        class: `seat-rect ${info.status}${adminMode && info.status === 'blocked' ? ' admin-blocked' : ''}`
      });
      g.appendChild(rect);

      // 차단 좌석에 × 표시 (사용자/관리자 모드 공통)
      if (info.status === 'blocked') {
        const xMark = makeSvgEl('text', {
          x: sx + S / 2, y: sy + S - 2,
          'text-anchor': 'middle',
          'font-size': 10, 'font-weight': 'bold',
          fill: adminMode ? '#7f1d1d' : '#ffffff',
          'font-family': 'Malgun Gothic,sans-serif',
          'pointer-events': 'none'
        });
        xMark.textContent = '×';
        g.appendChild(xMark);
      }
    });

    return g;
  }

  // ── 1층 전체 렌더링 ──────────────────────────────
  function renderFloor1(svg) {
    svg.innerHTML = '';

    const layout = ['가', '나', '다', '라'];
    const PAD = 40; // 좌우 패딩

    // 전체 너비 계산
    const totalSeatW = layout.reduce((acc, s) => acc + secWidth(s), 0)
                       + AISLE * (layout.length - 1);
    const totalW = totalSeatW + PAD * 2;

    // ── 무대 ──
    const stageH = 38;
    const stageY = 14;
    const stage  = makeSvgEl('rect', {
      x: PAD, y: stageY,
      width: totalSeatW, height: stageH,
      rx: 8, fill: 'url(#stageGrad)'
    });

    // 그라디언트 정의
    const defs = makeSvgEl('defs', {});
    const grad = makeSvgEl('linearGradient', {
      id: 'stageGrad', x1: '0%', y1: '0%', x2: '100%', y2: '0%'
    });
    const s1 = makeSvgEl('stop', { offset: '0%',   'stop-color': '#1a2a4a' });
    const s2 = makeSvgEl('stop', { offset: '50%',  'stop-color': '#2C3E50' });
    const s3 = makeSvgEl('stop', { offset: '100%', 'stop-color': '#1a2a4a' });
    grad.appendChild(s1); grad.appendChild(s2); grad.appendChild(s3);
    defs.appendChild(grad);
    svg.appendChild(defs);
    svg.appendChild(stage);

    const stageT = makeSvgEl('text', {
      x: PAD + totalSeatW / 2, y: stageY + 24,
      'text-anchor': 'middle', fill: 'white',
      'font-size': 14, 'font-weight': 'bold', 'letter-spacing': 6,
      'font-family': 'Malgun Gothic,sans-serif'
    });
    stageT.textContent = 'S T A G E';
    svg.appendChild(stageT);

    // ── 1층 레이블 ──
    const flLbl = makeSvgEl('text', {
      x: PAD + totalSeatW / 2, y: stageY + stageH + 16,
      'text-anchor': 'middle', fill: '#145285',
      'font-size': 12, 'font-weight': 'bold',
      'font-family': 'Malgun Gothic,sans-serif'
    });
    flLbl.textContent = '1 F L O O R';
    svg.appendChild(flLbl);

    // ── 구역들 ──
    const secY = stageY + stageH + 28;
    let curX = PAD;
    layout.forEach(sec => {
      const grp = buildSection(sec, curX, secY);
      if (grp) svg.appendChild(grp);
      curX += secWidth(sec) + AISLE;
    });

    // ── 가로 복도 흰색 밴드 (11행~12행 사이, 텍스트/점선 없음) ──
    const aisleRow = sections['가'] && sections['가'].aisle_after_row;
    if (aisleRow) {
      const aisleY = secY + disHeight('가') + aisleRow * STEP;
      // 구역 배경 위에 흰색 덮기 → 복도 공간이 흰색으로 보임
      const aisleRect = makeSvgEl('rect', {
        x: PAD - 2, y: aisleY,
        width: totalSeatW + 4, height: AISLE_H,
        fill: '#ffffff'
      });
      svg.appendChild(aisleRect);
    }

    // ── 행 번호 표시 (가 왼쪽, 라 오른쪽) ──
    const rowY0 = secY;
    const numSec = sections['가'];
    if (numSec) {
      const leftX  = PAD - 16;
      const rightX = PAD + totalSeatW + 6;
      for (let r = 0; r < numSec.rows; r++) {
        const rowLabel = String(r + 1).padStart(2, '0');
        const ao = aisleOffset('가', r + 1);   // 복도 이후 행 Y 오프셋
        const y  = rowY0 + disHeight('가') + r * STEP + ao + S - 2;
        // 왼쪽 번호 (가 구역 외곽)
        const ltxt = makeSvgEl('text', {
          x: leftX, y,
          'text-anchor': 'middle', fill: '#7a8fa6',
          'font-size': 9, 'font-family': 'Malgun Gothic,sans-serif'
        });
        ltxt.textContent = rowLabel;
        svg.appendChild(ltxt);
        // 오른쪽 번호 (라 구역 외곽)
        const rtxt = makeSvgEl('text', {
          x: rightX, y,
          'text-anchor': 'start', fill: '#7a8fa6',
          'font-size': 9, 'font-family': 'Malgun Gothic,sans-serif'
        });
        rtxt.textContent = rowLabel;
        svg.appendChild(rtxt);
      }
    }

    const totalH = secY + disHeight('가') + secHeight('가') + 24;
    svg.setAttribute('viewBox', `0 0 ${totalW} ${totalH}`);
    svg.setAttribute('width',  totalW);
    svg.setAttribute('height', totalH);
  }

  // ── 2층 전체 렌더링 ──────────────────────────────
  function renderFloor2(svg) {
    svg.innerHTML = '';

    const mainSecs = ['사', '아', '자', '차', '카', '타'];
    const PAD   = 20;
    const BAL_GAP = 16; // 발코니와 메인 구역 사이 간격

    // 발코니(마/바) 너비
    const balW = secWidth('마') || STEP * 2;

    // 메인 섹션 총 너비
    const mainW = mainSecs.reduce((a, s) => a + secWidth(s), 0)
                  + AISLE * (mainSecs.length - 1);

    const totalW = PAD + balW + BAL_GAP + mainW + BAL_GAP + balW + PAD;
    const secY   = 30;

    // ── 2층 레이블 ──
    const fl2 = makeSvgEl('text', {
      x: totalW / 2, y: 18,
      'text-anchor': 'middle', fill: '#145285',
      'font-size': 12, 'font-weight': 'bold',
      'font-family': 'Malgun Gothic,sans-serif'
    });
    fl2.textContent = '2 F L O O R';
    svg.appendChild(fl2);

    // ── 마 구역 (좌측 발코니) ──
    const maGrp = buildBalcony('마', PAD, secY);
    if (maGrp) svg.appendChild(maGrp);

    // ── 메인 구역들 (각 구역의 offsetX 기록) ──
    const secOffsetX = {};
    let curX = PAD + balW + BAL_GAP;
    mainSecs.forEach(sec => {
      secOffsetX[sec] = curX;
      const grp = buildSection(sec, curX, secY);
      if (grp) svg.appendChild(grp);
      curX += secWidth(sec) + AISLE;
    });

    // ── 자 구역: CONTROL BOOTH 오버레이 (rows 1-2 blocked 위에 덧그림) ──
    if (sections['자'] && secOffsetX['자'] !== undefined) {
      const cbX = secOffsetX['자'];
      const cbW = secWidth('자');
      const cbH = 2 * STEP - 1;   // rows 1-2 높이
      const cbRect = makeSvgEl('rect', {
        x: cbX - 2, y: secY - 2,
        width: cbW + 4, height: cbH + 4,
        rx: 5, fill: '#2C3E50', stroke: '#1a2a4a', 'stroke-width': 1.5
      });
      svg.appendChild(cbRect);
      const cbText = makeSvgEl('text', {
        x: cbX + cbW / 2, y: secY + cbH / 2 + 4,
        'text-anchor': 'middle', fill: '#FFD700',
        'font-size': 10, 'font-weight': 'bold', 'letter-spacing': 2,
        'font-family': 'Malgun Gothic,sans-serif'
      });
      cbText.textContent = 'CONTROL BOOTH';
      svg.appendChild(cbText);
    }

    // ── 아 구역: 우측 EXIT 아이콘 (rows 9-12, 7석 → 오른쪽 5열 공백) ──
    if (sections['아'] && secOffsetX['아'] !== undefined) {
      const ax = secOffsetX['아'];
      const sw = secWidth('아');           // = maxCols(아) * STEP = 12*STEP
      const exitW = (maxCols('아') - 7) * STEP;   // 5열 공백
      const exitX = ax + sw - exitW;
      const exitY = secY + 8 * STEP;      // row 9 시작
      const exitH = 4 * STEP;             // rows 9-12
      const exitR = makeSvgEl('rect', {
        x: exitX, y: exitY,
        width: exitW, height: exitH,
        rx: 4, fill: '#E8F5E9', stroke: '#81C784', 'stroke-width': 1, opacity: 0.85
      });
      svg.appendChild(exitR);
      const exitT = makeSvgEl('text', {
        x: exitX + exitW / 2, y: exitY + exitH / 2 + 4,
        'text-anchor': 'middle', fill: '#2E7D32',
        'font-size': 16, 'font-family': 'Malgun Gothic,sans-serif'
      });
      exitT.textContent = '🚶';
      svg.appendChild(exitT);
    }

    // ── 카 구역: 좌측 EXIT 아이콘 (rows 9-12, 7석 → 왼쪽 5열 공백) ──
    if (sections['카'] && secOffsetX['카'] !== undefined) {
      const kx  = secOffsetX['카'];
      const exitW = (maxCols('카') - 7) * STEP;   // 5열 공백
      const exitY = secY + 8 * STEP;
      const exitH = 4 * STEP;
      const exitR = makeSvgEl('rect', {
        x: kx, y: exitY,
        width: exitW, height: exitH,
        rx: 4, fill: '#E8F5E9', stroke: '#81C784', 'stroke-width': 1, opacity: 0.85
      });
      svg.appendChild(exitR);
      const exitT = makeSvgEl('text', {
        x: kx + exitW / 2, y: exitY + exitH / 2 + 4,
        'text-anchor': 'middle', fill: '#2E7D32',
        'font-size': 16, 'font-family': 'Malgun Gothic,sans-serif'
      });
      exitT.textContent = '🚶';
      svg.appendChild(exitT);
    }

    // ── 바 구역 (우측 발코니) ──
    const baX   = PAD + balW + BAL_GAP + mainW + BAL_GAP;
    const baGrp = buildBalcony('바', baX, secY);
    if (baGrp) svg.appendChild(baGrp);

    const maxMainH = Math.max(...mainSecs.map(s => secHeight(s)));
    const totalH   = secY + maxMainH + 30;
    svg.setAttribute('viewBox', `0 0 ${totalW} ${totalH}`);
    svg.setAttribute('width',  totalW);
    svg.setAttribute('height', totalH);
  }

  // ── 좌석 상태 / 사이드바 ─────────────────────────
  function updateSeatEl(id) {
    const el = document.querySelector(`[data-id="${id}"]`);
    if (!el) return;
    const info = seats[id];
    // selected 배열에 있으면 'selected' 클래스 (my_lock 포함)
    const cls = selected.includes(id) ? 'selected' : (info ? info.status : 'available');
    el.setAttribute('class', `seat-rect ${cls}`);
  }

  function updateSidebar() {
    const list     = document.getElementById('selectedList');
    const countEl  = document.getElementById('selectedCount');
    const bookBtn  = document.getElementById('bookBtn');
    if (!list) return;

    if (selected.length === 0) {
      list.innerHTML = '<li style="color:#999;text-align:center;padding:20px 0;font-size:14px;">좌석을 선택해주세요</li>';
    } else {
      list.innerHTML = selected.map(id => {
        const s = seats[id];
        return `<li>
          <span>🪑 ${s.section} 구역 ${s.seat_no}번</span>
          <button class="remove-seat" onclick="SeatMap.removeSeat('${id}')">×</button>
        </li>`;
      }).join('');
    }
    // 선택 수 표시: "현재선택 / 추가가능"
    if (countEl) countEl.textContent = selected.length;
    if (bookBtn) bookBtn.disabled = selected.length === 0;

    // 총 결제 금액 표시 (층별 금액 적용)
    const priceBar    = document.getElementById('totalPriceBar');
    const priceAmount = document.getElementById('totalPriceAmount');
    const priceDetail = document.getElementById('totalPriceDetail');
    if (priceBar) {
      if (selected.length > 0) {
        // 선택된 좌석의 층별 합계 계산
        let total = 0;
        let cnt1 = 0, cnt2 = 0;
        selected.forEach(function(id) {
          const s = seats[id];
          const fl = s ? s.floor : 1;
          const p  = _floorPrices[fl] || 10000;
          total += p;
          if (fl === 1) cnt1++; else cnt2++;
        });
        priceBar.style.display = 'block';
        if (priceAmount) priceAmount.textContent = total.toLocaleString('ko-KR') + '원';
        // 상세 설명: 층이 섞인 경우 층별로 표시
        let detail = '';
        if (cnt1 > 0 && cnt2 > 0) {
          detail = `1층 ${cnt1}석(${_floorPrices[1].toLocaleString('ko-KR')}원) + 2층 ${cnt2}석(${_floorPrices[2].toLocaleString('ko-KR')}원)`;
        } else if (cnt1 > 0) {
          detail = `${cnt1}석 × ${_floorPrices[1].toLocaleString('ko-KR')}원`;
        } else {
          detail = `${cnt2}석 × ${_floorPrices[2].toLocaleString('ko-KR')}원`;
        }
        if (priceDetail) priceDetail.textContent = detail;
      } else {
        priceBar.style.display = 'none';
      }
    }

    if (onSelectChange) onSelectChange(selected);
  }

  // ── 이벤트 ───────────────────────────────────────
  async function handleClick(e) {
    const rect = e.target.closest('[data-id]');
    if (!rect) return;
    const id = rect.getAttribute('data-id');
    if (!seats[id]) return;
    const st = seats[id].status;

    // ── 관리자 모드: 예매 완료 좌석 제외하고 차단/해제 토글 ──
    if (adminMode) {
      if (st === 'reserved' || st === 'mine') return;
      await toggleBlock(id);
      return;
    }

    // 예매완료/사용불가/타인 선점 좌석은 클릭 불가
    if (st === 'reserved' || st === 'blocked' || st === 'mine' || st === 'locked') return;

    // 큐 토큰 있으면 lock/unlock API 사용
    if (queueToken) {
      if (selected.includes(id)) {
        // 선택 해제 → unlock
        await unlockSeat(id);
      } else {
        // 새 선택 → lock
        await lockSeat(id);
      }
    } else {
      // 큐 토큰 없음(관리자 등) → 기존 로컬 토글
      toggleSeat(id);
    }
  }

  /** 좌석 선점 (서버에 lock 요청) */
  async function lockSeat(id) {
    // 최대 좌석 검사
    if (effectiveMax <= 0) {
      if (typeof window.showSeatLimitModal === 'function') {
        window.showSeatLimitModal(`이미 ${MAX_SEATS}석을 모두 예매하셨습니다.`, reservedCount, 0);
      }
      return;
    }
    if (selected.length >= effectiveMax) {
      if (typeof window.showSeatLimitModal === 'function') {
        window.showSeatLimitModal(`총 ${MAX_SEATS}석 한도를 초과할 수 없습니다.`, reservedCount, effectiveMax);
      }
      return;
    }

    try {
      const res  = await fetch('/api/seats/lock', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ seat_id: id, token: queueToken })  // id는 "가001" 같은 TEXT → parseInt 금지
      });

      if (res.ok) {
        seats[id].status = 'my_lock';
        if (!selected.includes(id)) selected.push(id);  // 연속 클릭 중복 방지
        updateSeatEl(id);
        updateSidebar();
      } else if (res.status === 409) {
        // 다른 사람이 이미 선점
        seats[id].status = 'locked';
        updateSeatEl(id);
        showAlert('이미 다른 분이 선택 중인 좌석입니다.', 'warning');
      } else if (res.status === 403) {
        // 큐 세션 만료
        showAlert('예매 세션이 만료되었습니다. 대기열로 돌아갑니다.', 'danger');
        setTimeout(() => location.href = '/queue', 2000);
      }
    } catch (err) {
      console.error('Lock error:', err);
    }
  }

  /** 좌석 선점 해제 (서버에 unlock 요청) */
  async function unlockSeat(id) {
    const idx = selected.indexOf(id);
    if (idx < 0) return;
    selected.splice(idx, 1);

    try {
      await fetch('/api/seats/unlock', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ seat_id: id, token: queueToken })  // TEXT id 그대로 전달
      });
    } catch (err) {
      console.error('Unlock error:', err);
    }

    seats[id].status = 'available';
    updateSeatEl(id);
    updateSidebar();
  }

  /** 5초마다 좌석 상태 갱신 (다른 사람의 lock/unlock 반영) */
  async function refreshSeats() {
    if (!currentSvgId) return;
    try {
      const url = `/api/seats/${currentFloor}` + (queueToken ? `?token=${encodeURIComponent(queueToken)}` : '');
      const res  = await fetch(url);
      const data = await res.json();
      const newSeats = data.seats || {};

      Object.keys(newSeats).forEach(id => {
        const newInfo = newSeats[id];
        const oldInfo = seats[id];
        if (!oldInfo) return;

        if (selected.includes(id)) {
          // 내가 선택 중인 좌석: 서버에서 reserved/mine으로 바뀌면 선점 해제된 것
          if (newInfo.status === 'reserved' || newInfo.status === 'mine') {
            seats[id] = newInfo;
            selected.splice(selected.indexOf(id), 1);
            updateSeatEl(id);
          }
          // my_lock 유지 → 그대로
        } else {
          if (oldInfo.status !== newInfo.status) {
            seats[id] = newInfo;
            updateSeatEl(id);
          }
        }
      });
      updateSidebar();
    } catch (e) { /* 무시 */ }
  }

  // 툴팁
  const tooltip = document.createElement('div');
  tooltip.className = 'seat-tooltip';
  document.body.appendChild(tooltip);

  /** 관리자 전용: 좌석 차단/해제 토글 API 호출 */
  async function toggleBlock(id) {
    try {
      const res  = await fetch('/api/admin/seats/toggle-block', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ seat_id: id })
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        seats[id].status = data.status;
        rerenderCurrent();
        // 차단 카운트 업데이트 이벤트
        if (typeof window.onAdminSeatToggle === 'function') {
          const blockedCount = Object.values(seats).filter(s => s.status === 'blocked').length;
          window.onAdminSeatToggle({ seatId: id, newStatus: data.status, blockedCount });
        }
      } else {
        showAlert(data.error || '좌석 차단 변경에 실패했습니다.', 'warning');
      }
    } catch (err) {
      console.error('toggleBlock error:', err);
      showAlert('네트워크 오류가 발생했습니다.', 'danger');
    }
  }

  /** 현재 층 SVG를 API 호출 없이 재렌더링 (좌석 상태는 메모리 seats 기준) */
  function rerenderCurrent() {
    const svg = document.getElementById(currentSvgId);
    if (!svg) return;
    if (currentFloor === 1) renderFloor1(svg);
    else                    renderFloor2(svg);
    // SVG 교체 없이 innerHTML만 갱신 → 이벤트 리스너는 이미 svg 요소에 부착돼 있어 유지됨
  }

  function handleMouseMove(e) {
    const rect = e.target.closest('[data-id]');
    if (!rect) { tooltip.style.display = 'none'; return; }
    const id   = rect.getAttribute('data-id');
    const sec  = rect.getAttribute('data-sec');
    const no   = rect.getAttribute('data-no');
    const info = seats[id];
    if (!info) return;

    let tipText;
    if (adminMode) {
      const adminMap = {
        available: '클릭하여 차단 등록',
        blocked:   '클릭하여 차단 해제',
        reserved:  '예매완료 (변경불가)',
        locked:    '선점 중',
        mine:      '내 좌석'
      };
      tipText = `${sec} 구역 ${no}번 | ${adminMap[info.status] || info.status}`;
    } else {
      const stMap = {
        available: '예매가능', reserved: '예매완료',
        blocked: '예매 불가', mine: '내 좌석', selected: '선택됨',
        locked: '다른분 선택 중', my_lock: '선택됨(선점완료)'
      };
      const st = selected.includes(id) ? 'selected' : info.status;
      tipText = `${sec} 구역 ${no}번 | ${stMap[st] || st}`;
    }
    tooltip.textContent = tipText;
    tooltip.style.display = 'block';
    tooltip.style.left = (e.clientX + 12) + 'px';
    tooltip.style.top  = (e.clientY - 28) + 'px';
  }

  function handleMouseLeave() { tooltip.style.display = 'none'; }

  // ── 공개 API ─────────────────────────────────────
  async function load(floor, svgId) {
    currentFloor = floor;
    currentSvgId = svgId;
    const svg = document.getElementById(svgId);
    if (!svg) return;

    svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="#999" font-size="14">로딩 중...</text>';

    // 좌석 폴링 재시작
    stopSeatPoll();

    try {
      const url = `/api/seats/${floor}` + (queueToken ? `?token=${encodeURIComponent(queueToken)}` : '');
      const res  = await fetch(url);
      const data = await res.json();
      // ── 층 전환 시 다른 층 선택 유지: replace 대신 merge ──
      const thisFloorIds = new Set(Object.keys(data.seats));
      // 이 층에 속하는 기존 selected 제거 후 새 데이터로 교체
      selected = selected.filter(function(id) { return !thisFloorIds.has(String(id)); });
      // 새로 로드된 층의 seats를 전체 seats에 병합
      Object.assign(seats, data.seats);
      // 서버의 my_lock 좌석을 selected에 복원 (새로고침 대응)
      Object.keys(data.seats).forEach(function(id) {
        if (data.seats[id].status === 'my_lock' && !selected.includes(id)) {
          selected.push(id);
        }
      });

      sections      = data.sections;
      reservedCount = data.reserved_count || 0;
      const isAdmin = data.is_admin || false;
      effectiveMax  = isAdmin
        ? Infinity
        : Math.max(0, (data.max_seats || MAX_SEATS) - reservedCount);

      if (floor === 1) renderFloor1(svg);
      else             renderFloor2(svg);

      // 층 전환 시 이벤트 리스너 중복 등록 방지: 먼저 제거 후 재등록
      svg.removeEventListener('click',      handleClick);
      svg.removeEventListener('mousemove',  handleMouseMove);
      svg.removeEventListener('mouseleave', handleMouseLeave);
      svg.addEventListener('click',      handleClick);
      svg.addEventListener('mousemove',  handleMouseMove);
      svg.addEventListener('mouseleave', handleMouseLeave);

      updateSidebar();

      // 5초 폴링 시작 (큐 토큰 있을 때만)
      if (queueToken) startSeatPoll();

      // 로드 완료 콜백 (booking.html UI 업데이트용)
      if (onLoadCallback) onLoadCallback({ reservedCount, effectiveMax, maxSeats: data.max_seats || MAX_SEATS });
    } catch (err) {
      svg.innerHTML = `<text x="50%" y="50%" fill="red" font-size="14">${err.message}</text>`;
    }
  }

  function startSeatPoll() {
    stopSeatPoll();
    seatPollTimer = setInterval(refreshSeats, 5000);
  }
  function stopSeatPoll() {
    if (seatPollTimer) { clearInterval(seatPollTimer); seatPollTimer = null; }
  }

  function toggleSeat(id) {
    if (!seats[id]) return;
    const idx = selected.indexOf(id);
    if (idx >= 0) {
      // 선택 해제
      selected.splice(idx, 1);
    } else {
      // 추가 선택 가능 여부 검사
      if (effectiveMax <= 0) {
        // 이미 10석 모두 예매한 경우
        if (typeof window.showSeatLimitModal === 'function') {
          window.showSeatLimitModal(
            `이미 ${MAX_SEATS}석을 모두 예매하셨습니다.`,
            reservedCount, 0
          );
        } else {
          showAlert(`이미 ${MAX_SEATS}석을 모두 예매하셨습니다.`, 'warning');
        }
        return;
      }
      if (selected.length >= effectiveMax) {
        // 이번 선택이 추가 가능 한도를 초과한 경우
        if (typeof window.showSeatLimitModal === 'function') {
          window.showSeatLimitModal(
            `총 ${MAX_SEATS}석 한도를 초과할 수 없습니다.`,
            reservedCount, effectiveMax
          );
        } else {
          showAlert(`최대 ${MAX_SEATS}석까지 예매 가능합니다.`, 'warning');
        }
        return;
      }
      selected.push(id);
    }
    updateSeatEl(id);
    updateSidebar();
  }

  function getSelected()  { return [...selected]; }

  async function clearSelected() {
    const prev = [...selected];
    selected = [];

    if (queueToken && prev.length > 0) {
      // 선점된 좌석 일괄 해제
      await Promise.all(prev.map(id =>
        fetch('/api/seats/unlock', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ seat_id: id, token: queueToken })  // TEXT id 그대로 전달
        }).then(() => { if (seats[id]) seats[id].status = 'available'; })
          .catch(() => {})
      ));
    } else {
      prev.forEach(id => { if (seats[id]) seats[id].status = 'available'; });
    }

    prev.forEach(id => updateSeatEl(id));
    updateSidebar();
  }

  function onSelect(cb) { onSelectChange = cb; }
  function onLoad(cb)   { onLoadCallback  = cb; }
  function getEffectiveMax()  { return effectiveMax; }
  function getReservedCount() { return reservedCount; }

  /** booking.html에서 큐 토큰 주입 */
  function setToken(token) {
    queueToken = token || '';
  }

  /** booking.html에서 층별 금액 주입 { floor1: number, floor2: number } */
  function setPrices(prices) {
    if (prices && prices.floor1) _floorPrices[1] = parseInt(prices.floor1) || 10000;
    if (prices && prices.floor2) _floorPrices[2] = parseInt(prices.floor2) || 10000;
  }

  /** admin/seats.html에서 관리자 모드 활성화 */
  function setAdminMode(flag) {
    adminMode = !!flag;
  }

  /** 현재 seats 데이터에서 차단된 좌석 수 반환 */
  function getBlockedCount() {
    return Object.values(seats).filter(s => s.status === 'blocked').length;
  }

  function showAlert(msg, type = 'warning') {
    const el = document.getElementById('bookingAlert');
    if (!el) { alert(msg); return; }
    el.textContent = msg;
    el.className   = `alert alert-${type} show`;
    setTimeout(() => el.classList.remove('show'), 3500);
  }

  /** 사이드바 X 버튼용: 큐 토큰 유무에 따라 unlock API 또는 로컬 토글 */
  async function removeSeat(id) {
    if (queueToken && seats[id] && seats[id].status === 'my_lock') {
      await unlockSeat(id);   // 서버 unlock + 로컬 제거 + UI 갱신
    } else {
      toggleSeat(id);         // 큐 없을 때(관리자 등) 로컬 제거만
    }
  }

  return {
    load, setToken, setPrices, setAdminMode, toggleSeat, removeSeat, getSelected, clearSelected,
    onSelect, onLoad, getEffectiveMax, getReservedCount,
    stopSeatPoll, rerenderCurrent, getBlockedCount
  };
})();
