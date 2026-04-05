const shogiSocket = io();
let currentShogiGameId = null;

let shogiState = null;
let selectedFrom = null;
let selectedDropPiece = null;
let shogiAIInfo = { black_ai: null, white_ai: null, engine_scope: 'server' };
let previousTurnPlayer = null;
let suppressTurnAnimation = true;
let boardTransitionTimer = null;
let turnIndicatorTimer = null;
let thinkingHideTimer = null;
let resizeSyncTimer = null;
let browserAITurnToken = 0;
let browserAITurnRunning = false;
let thinkingStartedAt = 0;
let isThinkingIndicatorVisible = false;
let autoRotateBoard = false;
let shogiMatchmakingInProgress = false;
let shogiPlayerName = '';
let shogiPassword = '';
let shogiAssignedSeat = null;
let shogiAssignedRole = null;
let shogiIsCreator = false;
let shogiOpponentName = '';
let shogiGameMode = null;
let shogiMatchResumeAllowed = false;
let shogiSingleSeat = 'first';
let shogiRoleChoicePending = false;
const SHOGI_MATCH_PROFILE_KEY = 'shogi-match-profile';

const TURN_ROTATION_MS = 760;
const AUTO_ROTATE_STORAGE_KEY = 'shogi-auto-rotate';
const SHOGI_ENGINE_LABELS = {
    rule_based: 'Rule Based',
    minimax: 'Minimax',
    mcts: 'MCTS',
    ml: 'ML Policy (CPU)',
    onnx: 'ML Policy (CPU)',
    none: 'AI',
};

function normalizeShogiEngine(engine) {
    return engine === 'onnx' ? 'ml' : engine;
}

function isServerBackedShogiEngine(engine) {
    const normalized = normalizeShogiEngine(engine || 'none');
    return normalized === 'ml';
}

function resolveSingleplayerEngineScopeFromControls() {
    const blackEnabled = !!document.getElementById('black-ai-enable')?.checked;
    const whiteEnabled = !!document.getElementById('white-ai-enable')?.checked;
    const blackEngine = document.getElementById('black-ai-engine')?.value || 'none';
    const whiteEngine = document.getElementById('white-ai-engine')?.value || 'none';

    const usesServerEngine = (blackEnabled && isServerBackedShogiEngine(blackEngine))
        || (whiteEnabled && isServerBackedShogiEngine(whiteEngine));
    return usesServerEngine ? 'server' : 'browser';
}

const PIECE_TEXT = {
    1: '歩',
    2: '香',
    3: '桂',
    4: '銀',
    5: '金',
    6: '角',
    7: '飛',
    8: '玉',
    9: 'と',
    10: '杏',
    11: '圭',
    12: '全',
    13: '馬',
    14: '龍'
};

const HAND_ORDER = ['R', 'B', 'G', 'S', 'N', 'L', 'P'];
const HAND_JP = {
    R: '飛',
    B: '角',
    G: '金',
    S: '銀',
    N: '桂',
    L: '香',
    P: '歩'
};

function setStatus(msg) {
    document.getElementById('status-message').textContent = msg;
}

function setShogiMatchStatus(message, isError = false) {
    window.GameClientCommon.setStatusText('shogi-match-status-text', message, isError, '#2f4f3a', '#a93c34');
}

function setShogiModeStatus(message, isError = false) {
    window.GameClientCommon.setStatusText('shogi-mode-status-text', message, isError, '#2f4f3a', '#a93c34');
}

function setShogiSingleStatus(message, isError = false) {
    window.GameClientCommon.setStatusText('shogi-single-status-text', message, isError, '#2f4f3a', '#a93c34');
}

function setShogiViewState(view) {
    const modePanel = document.getElementById('shogi-mode-panel');
    const singlePanel = document.getElementById('shogi-singleplayer-panel');
    const matchPanel = document.getElementById('shogi-matchmaking-panel');
    const mainPanel = document.getElementById('shogi-main-panel');
    if (!modePanel || !singlePanel || !matchPanel || !mainPanel) return;

    modePanel.classList.toggle('hidden', view !== 'mode');
    singlePanel.classList.toggle('hidden', view !== 'single-setup');
    matchPanel.classList.toggle('hidden', view !== 'matchmaking');
    mainPanel.classList.toggle('hidden', view !== 'game');
}

function setShogiRoleButtonsDisabled(disabled) {
    const firstBtn = document.getElementById('shogi-choose-first-btn');
    const secondBtn = document.getElementById('shogi-choose-second-btn');
    if (firstBtn) firstBtn.disabled = disabled;
    if (secondBtn) secondBtn.disabled = disabled;
}

function updateShogiSingleSeatButtons() {
    const firstBtn = document.getElementById('shogi-single-first-btn');
    const secondBtn = document.getElementById('shogi-single-second-btn');
    if (!firstBtn || !secondBtn) return;
    firstBtn.classList.toggle('secondary', shogiSingleSeat !== 'first');
    secondBtn.classList.toggle('secondary', shogiSingleSeat !== 'second');
}

function selectShogiSingleSeat(seat) {
    shogiSingleSeat = seat === 'second' ? 'second' : 'first';
    updateShogiSingleSeatButtons();
}

function setShogiAIControlsEnabled(enabled) {
    const ids = [
        'black-ai-enable',
        'white-ai-enable',
        'black-ai-engine',
        'white-ai-engine',
        'black-ai-difficulty',
        'white-ai-difficulty',
        'apply-ai-btn',
        'clear-ai-btn',
    ];
    ids.forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = !enabled;
        }
    });
}

function setShogiGameMode(mode) {
    if (mode !== 'singleplayer' && mode !== 'multiplayer') {
        shogiGameMode = null;
        shogiMatchResumeAllowed = false;
        syncAutoRotateToggleState();
        setShogiViewState('mode');
        return;
    }

    shogiGameMode = mode;
    syncAutoRotateToggleState();
    if (mode === 'singleplayer') {
        setShogiViewState('single-setup');
        setShogiModeStatus('一人プレイを選択しました');
        setShogiSingleStatus('先手/後手とAIモデルを選択してください');
        setShogiAIControlsEnabled(true);
        return;
    }

    setShogiViewState('matchmaking');
    setShogiModeStatus('マルチプレイを選択しました');
    setShogiMatchStatus('プレイヤー名と合言葉を入力してください');
    setShogiAIControlsEnabled(false);
}

function setShogiMatchButtons(waiting) {
    const startBtn = document.getElementById('shogi-start-match-btn');
    const cancelBtn = document.getElementById('shogi-cancel-match-btn');
    if (!startBtn || !cancelBtn) return;
    startBtn.disabled = waiting;
    cancelBtn.disabled = !waiting;
}

function toggleShogiPanels(visible) {
    if (visible) {
        setShogiViewState('game');
    } else if (shogiGameMode === 'singleplayer') {
        setShogiViewState('single-setup');
    } else if (shogiGameMode === 'multiplayer') {
        setShogiViewState('matchmaking');
    } else {
        setShogiViewState('mode');
    }
}

function loadShogiMatchProfile() {
    const profile = window.GameClientCommon.readProfile(SHOGI_MATCH_PROFILE_KEY);
    shogiPlayerName = profile.player_name;
    shogiPassword = profile.password;
}

function persistShogiMatchProfile(playerName, password) {
    shogiPlayerName = playerName;
    shogiPassword = password;
    window.GameClientCommon.writeProfile(SHOGI_MATCH_PROFILE_KEY, playerName, password);
}

function showShogiRoleModal(show, timeoutSeconds = 15) {
    const modal = document.getElementById('shogi-role-modal');
    const desc = document.getElementById('shogi-role-modal-description');
    if (!modal) return;
    modal.classList.toggle('hidden', !show);
    if (show && desc) {
        desc.textContent = `部屋作成者として先手/後手を選んでください（${timeoutSeconds}秒以内）`;
    }
}

function requestShogiMatchStart() {
    const nameInput = document.getElementById('shogi-player-name-input');
    const passwordInput = document.getElementById('shogi-match-password-input');
    const playerName = (nameInput?.value || '').trim();
    const password = (passwordInput?.value || '').trim();

    if (!playerName) {
        setShogiMatchStatus('プレイヤー名を入力してください', true);
        return;
    }
    if (!password) {
        setShogiMatchStatus('合言葉を入力してください', true);
        return;
    }

    setShogiGameMode('multiplayer');
    shogiMatchResumeAllowed = true;
    persistShogiMatchProfile(playerName, password);
    shogiMatchmakingInProgress = true;
    currentShogiGameId = null;
    shogiAssignedSeat = null;
    shogiAssignedRole = null;
    shogiIsCreator = false;
    shogiOpponentName = '';
    setShogiMatchButtons(true);
    setShogiMatchStatus('マッチング待機中です...');

    shogiSocket.emit('start_matchmaking', {
        player_name: playerName,
        password,
        game_type: 'shogi'
    });
}

function requestShogiMatchCancel() {
    shogiMatchmakingInProgress = false;
    shogiMatchResumeAllowed = false;
    setShogiMatchButtons(false);
    shogiSocket.emit('cancel_matchmaking', {});
}

function resetShogiEntryMode() {
    shogiMatchmakingInProgress = false;
    shogiMatchResumeAllowed = false;
    currentShogiGameId = null;
    shogiAssignedSeat = null;
    shogiAssignedRole = null;
    shogiIsCreator = false;
    shogiOpponentName = '';
    setShogiRoleButtonsDisabled(false);
    showShogiRoleModal(false);
    setShogiMatchButtons(false);
    setShogiGameMode(null);
    toggleShogiPanels(false);
    clearUiForPendingState('対戦モードを選択してください');
}

function chooseShogiRole(role) {
    if (shogiGameMode !== 'multiplayer') {
        setShogiMatchStatus('マルチプレイモード未選択です', true);
        return;
    }
    if (!currentShogiGameId) {
        setShogiMatchStatus('ゲームIDが設定されていません。マッチング から再度開始してください', true);
        return;
    }
    if (shogiRoleChoicePending) {
        setShogiMatchStatus('先手/後手選択待機中です。しばらくお待ちください', true);
        return;
    }
    shogiRoleChoicePending = true;
    setShogiRoleButtonsDisabled(true);
    setShogiMatchStatus('先手/後手を確定しています...');
    shogiSocket.emit('choose_role_after_match', { game_id: currentShogiGameId, role });
}

function requestShogiSingleStart() {
    const engineSelect = document.getElementById('shogi-single-ai-engine');
    if (!engineSelect) {
        setShogiSingleStatus('一人プレイ設定の初期化に失敗しました', true);
        return;
    }

    setShogiGameMode('singleplayer');
    currentShogiGameId = `shogi-single-${Date.now()}`;
    shogiAssignedSeat = shogiSingleSeat;
    shogiAssignedRole = shogiSingleSeat === 'first' ? 'sente' : 'gote';
    shogiOpponentName = 'AI';
    shogiRoleChoicePending = false;
    setShogiRoleButtonsDisabled(false);
    showShogiRoleModal(false);
    toggleShogiPanels(true);
    clearUiForPendingState('一人プレイを開始しています...');
    syncAutoRotateToggleState();

    shogiSocket.emit('create_game', {
        game_id: currentShogiGameId,
        game_type: 'shogi',
        mode: 'singleplayer'
    });

    const selectedEngine = normalizeShogiEngine(engineSelect.value || 'rule_based');
    const engineScope = isServerBackedShogiEngine(selectedEngine) ? 'server' : 'browser';
    const aiColor = shogiSingleSeat === 'first' ? 'white' : 'black';
    const humanColor = aiColor === 'black' ? 'white' : 'black';

    shogiSocket.emit('set_ai', {
        game_id: currentShogiGameId,
        color: aiColor,
        algorithm: selectedEngine,
        engine: selectedEngine,
        difficulty: 'medium',
        depth: 2,
        iterations: 220,
        time_budget_ms: 800,
        engine_scope: engineScope
    });

    shogiSocket.emit('set_ai', {
        game_id: currentShogiGameId,
        color: humanColor,
        algorithm: 'none',
        engine: 'none',
        difficulty: 'medium',
        engine_scope: engineScope
    });

    shogiSocket.emit('get_ai_info', { game_id: currentShogiGameId });
    setStatus(`一人プレイ開始: あなたは${shogiAssignedRole === 'sente' ? '先手' : '後手'}です`);
}

function setThinkingIndicator(active, player = null, algorithm = null) {
    const indicator = document.getElementById('thinking-indicator');
    const text = document.getElementById('thinking-text');

    if (!indicator || !text) {
        return;
    }

    if (active) {
        if (thinkingHideTimer) {
            clearTimeout(thinkingHideTimer);
            thinkingHideTimer = null;
        }

        isThinkingIndicatorVisible = true;
        thinkingStartedAt = Date.now();
        indicator.classList.remove('hidden');

        const playerText = player === 'black' ? '先手' : player === 'white' ? '後手' : 'AI';
        const algorithmText = SHOGI_ENGINE_LABELS[normalizeShogiEngine(algorithm)] || 'AI';
        text.textContent = `${playerText}AI (${algorithmText}) が思考中です...`;
        return;
    }

    if (!isThinkingIndicatorVisible) {
        indicator.classList.add('hidden');
        return;
    }

    const elapsed = Date.now() - thinkingStartedAt;
    const remaining = Math.max(0, 500 - elapsed);

    if (thinkingHideTimer) {
        clearTimeout(thinkingHideTimer);
    }

    thinkingHideTimer = setTimeout(() => {
        indicator.classList.add('hidden');
        isThinkingIndicatorVisible = false;
        thinkingHideTimer = null;
    }, remaining);
}

function cancelBrowserAITurn() {
    browserAITurnToken += 1;
    browserAITurnRunning = false;
}

function isBrowserAIScope() {
    return (shogiAIInfo.engine_scope || 'server') === 'browser';
}

function getCurrentTurnColor() {
    if (!shogiState) {
        return null;
    }
    return shogiState.current_player === 1 ? 'black' : 'white';
}

function getCurrentTurnAIConfig() {
    const color = getCurrentTurnColor();
    if (!color) {
        return null;
    }
    return color === 'black' ? shogiAIInfo.black_ai : shogiAIInfo.white_ai;
}

function shouldRunBrowserAITurn() {
    if (shogiGameMode !== 'singleplayer') {
        return false;
    }
    if (!currentShogiGameId || !shogiState || shogiState.game_over) {
        return false;
    }
    if (!isBrowserAIScope()) {
        return false;
    }
    if (!Array.isArray(shogiState.valid_moves) || shogiState.valid_moves.length === 0) {
        return false;
    }
    const aiConfig = getCurrentTurnAIConfig();
    if (!aiConfig) {
        return false;
    }
    const engine = normalizeShogiEngine(aiConfig.engine || aiConfig.algorithm || 'none');
    return engine !== 'none';
}

function triggerBrowserAITurnIfNeeded() {
    if (!shouldRunBrowserAITurn() || browserAITurnRunning) {
        return;
    }

    const aiConfig = getCurrentTurnAIConfig();
    const aiColor = getCurrentTurnColor();
    const turnToken = browserAITurnToken + 1;
    browserAITurnToken = turnToken;
    browserAITurnRunning = true;

    setThinkingIndicator(true, aiColor, aiConfig ? (aiConfig.engine || aiConfig.algorithm) : null);

    window.setTimeout(() => {
        if (turnToken !== browserAITurnToken) {
            return;
        }

        try {
            const selector = window.ShogiBrowserAI && window.ShogiBrowserAI.selectMove;
            if (!selector) {
                setStatus('ブラウザAIが初期化されていません');
                setThinkingIndicator(false);
                browserAITurnRunning = false;
                return;
            }

            const selectedMove = selector(shogiState, aiConfig || {});
            if (!selectedMove) {
                setThinkingIndicator(false);
                browserAITurnRunning = false;
                return;
            }

            shogiSocket.emit('make_move', {
                game_id: currentShogiGameId,
                move: {
                    from: selectedMove.from,
                    to: selectedMove.to,
                    drop_piece: selectedMove.drop_piece,
                    promote: !!selectedMove.promote,
                }
            });
            setThinkingIndicator(false);
        } catch (error) {
            console.error('Browser shogi AI move selection failed:', error);
            setStatus('ブラウザAIの手生成でエラーが発生しました');
            setThinkingIndicator(false);
        } finally {
            if (turnToken === browserAITurnToken) {
                browserAITurnRunning = false;
            }
        }
    }, 40);
}

function initBoard() {
    const board = document.getElementById('shogi-board');
    board.innerHTML = '';
    for (let row = 0; row < 9; row++) {
        for (let col = 0; col < 9; col++) {
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.className = 'shogi-cell';
            cell.dataset.row = row;
            cell.dataset.col = col;
            cell.addEventListener('click', onBoardCellClick);
            board.appendChild(cell);
        }
    }
}

function clearUiForPendingState(message) {
    cancelBrowserAITurn();
    shogiState = null;
    selectedFrom = null;
    selectedDropPiece = null;
    previousTurnPlayer = null;
    suppressTurnAnimation = true;

    if (boardTransitionTimer) {
        clearTimeout(boardTransitionTimer);
        boardTransitionTimer = null;
    }

    if (turnIndicatorTimer) {
        clearTimeout(turnIndicatorTimer);
        turnIndicatorTimer = null;
    }

    initBoard();

    const board = document.getElementById('shogi-board');
    board.classList.remove('board-rotated', 'turn-transition');

    const turnEl = document.getElementById('turn-text');
    turnEl.classList.remove('turn-switch');

    const turnBox = turnEl.closest('.turn-box');
    if (turnBox) {
        turnBox.classList.remove('turn-switch');
    }

    document.getElementById('turn-text').textContent = '対局情報を取得中...';
    document.getElementById('black-hands').innerHTML = '';
    document.getElementById('white-hands').innerHTML = '';
    setThinkingIndicator(false);
    setStatus(message);
}

function loadAutoRotatePreference() {
    const toggle = document.getElementById('auto-rotate-toggle');
    if (!toggle) {
        return;
    }

    try {
        const saved = localStorage.getItem(AUTO_ROTATE_STORAGE_KEY);
        autoRotateBoard = saved === 'true';
    } catch (error) {
        autoRotateBoard = false;
    }

    toggle.checked = autoRotateBoard;
}

function persistAutoRotatePreference() {
    try {
        localStorage.setItem(AUTO_ROTATE_STORAGE_KEY, autoRotateBoard ? 'true' : 'false');
    } catch (error) {
        // Ignore storage errors (privacy mode, quota, etc.) and keep runtime state only.
    }
}

function shouldRotateBoard() {
    if (shogiAssignedSeat !== 'second') {
        return false;
    }

    // In multiplayer, orientation is fixed by assigned side.
    if (shogiGameMode === 'multiplayer') {
        return true;
    }

    return autoRotateBoard;
}

function syncAutoRotateToggleState() {
    const toggle = document.getElementById('auto-rotate-toggle');
    if (!toggle) {
        return;
    }

    const forceByMultiplayer = shogiGameMode === 'multiplayer';
    toggle.disabled = forceByMultiplayer;
    toggle.checked = forceByMultiplayer ? shouldRotateBoard() : autoRotateBoard;
}

function updateBoardOrientation(animateTurnChange) {
    const board = document.getElementById('shogi-board');
    const shouldRotate = shouldRotateBoard();

    board.classList.toggle('board-rotated', shouldRotate);

    if (!animateTurnChange) {
        board.classList.remove('turn-transition');
        return;
    }

    board.classList.remove('turn-transition');
    void board.offsetWidth;
    board.classList.add('turn-transition');

    if (boardTransitionTimer) {
        clearTimeout(boardTransitionTimer);
    }

    boardTransitionTimer = setTimeout(() => {
        board.classList.remove('turn-transition');
        boardTransitionTimer = null;
    }, TURN_ROTATION_MS + 40);
}

function animateTurnIndicator(animateTurnChange) {
    const turnEl = document.getElementById('turn-text');
    const turnBox = turnEl.closest('.turn-box');

    if (!animateTurnChange) {
        turnEl.classList.remove('turn-switch');
        if (turnBox) {
            turnBox.classList.remove('turn-switch');
        }
        return;
    }

    turnEl.classList.remove('turn-switch');
    if (turnBox) {
        turnBox.classList.remove('turn-switch');
    }
    void turnEl.offsetWidth;
    turnEl.classList.add('turn-switch');
    if (turnBox) {
        turnBox.classList.add('turn-switch');
    }

    if (turnIndicatorTimer) {
        clearTimeout(turnIndicatorTimer);
    }

    turnIndicatorTimer = setTimeout(() => {
        turnEl.classList.remove('turn-switch');
        if (turnBox) {
            turnBox.classList.remove('turn-switch');
        }
        turnIndicatorTimer = null;
    }, TURN_ROTATION_MS + 80);
}

function syncBoardLayoutAfterResize() {
    const board = document.getElementById('shogi-board');
    if (!board) {
        return;
    }

    if (boardTransitionTimer) {
        clearTimeout(boardTransitionTimer);
        boardTransitionTimer = null;
    }
    board.classList.remove('turn-transition');

    const turnEl = document.getElementById('turn-text');
    if (turnEl) {
        turnEl.classList.remove('turn-switch');
    }

    updateBoardOrientation(false);
}

function setupWindowResizeSync() {
    window.addEventListener('resize', () => {
        if (resizeSyncTimer) {
            clearTimeout(resizeSyncTimer);
        }

        resizeSyncTimer = setTimeout(() => {
            resizeSyncTimer = null;
            syncBoardLayoutAfterResize();
        }, 120);
    });
}

function setupSocket() {
    shogiSocket.on('connect', () => {
        loadShogiMatchProfile();
        const nameInput = document.getElementById('shogi-player-name-input');
        const passwordInput = document.getElementById('shogi-match-password-input');
        if (nameInput && shogiPlayerName) nameInput.value = shogiPlayerName;
        if (passwordInput && shogiPassword) passwordInput.value = shogiPassword;

        if (shogiMatchResumeAllowed && shogiGameMode === 'multiplayer' && shogiPlayerName && shogiPassword) {
            shogiMatchmakingInProgress = true;
            setShogiMatchButtons(true);
            setShogiMatchStatus('再接続中です。対局への復帰を試みています...');
            shogiSocket.emit('start_matchmaking', {
                player_name: shogiPlayerName,
                password: shogiPassword,
                game_type: 'shogi'
            });
            return;
        }

        setShogiMatchButtons(false);
        if (!currentShogiGameId) {
            setShogiGameMode(null);
            toggleShogiPanels(false);
            clearUiForPendingState('接続しました。対戦モードを選択してください');
        }
    });

    shogiSocket.on('disconnect', () => {
        cancelBrowserAITurn();
        clearUiForPendingState('接続が切断されました。再接続を待っています...');
        setShogiMatchStatus('接続が切断されました。再接続中です...', true);
    });

    shogiSocket.on('matchmaking_status', (data) => {
        const status = data?.status || 'idle';
        const message = data?.message || '';
        if (status === 'waiting') {
            shogiMatchmakingInProgress = true;
            setShogiMatchButtons(true);
            setShogiMatchStatus(message || '相手を待っています...');
            return;
        }
        shogiMatchmakingInProgress = false;
        setShogiMatchButtons(false);
        setShogiMatchStatus(message || '待機を終了しました');
    });

    shogiSocket.on('match_found', (data) => {
        currentShogiGameId = data.game_id;
        shogiOpponentName = data.opponent_name || '';
        shogiIsCreator = !!data.is_creator;
        shogiMatchmakingInProgress = false;
        setShogiMatchButtons(false);
        setShogiMatchStatus(`マッチ成立: ${shogiOpponentName} と対戦します`);
    });

    shogiSocket.on('role_choice_required', (data) => {
        shogiRoleChoicePending = false;
        setShogiRoleButtonsDisabled(false);
        if (shogiIsCreator) {
            showShogiRoleModal(true, data?.timeout_seconds || 15);
        }
    });

    shogiSocket.on('role_waiting', (data) => {
        showShogiRoleModal(false);
        setShogiMatchStatus(data?.message || '部屋作成者が先手/後手を選択中です...');
    });

    shogiSocket.on('role_assigned', (data) => {
        shogiRoleChoicePending = false;
        setShogiRoleButtonsDisabled(false);
        shogiAssignedSeat = data.your_seat;
        shogiAssignedRole = data.your_role;
        shogiOpponentName = data.opponent_name || shogiOpponentName;
        setShogiAIControlsEnabled(false);
        toggleShogiPanels(true);
        showShogiRoleModal(false);
        setStatus(`対戦相手: ${shogiOpponentName} / あなた: ${shogiAssignedRole}`);
        clearUiForPendingState('対局情報を取得中...');
        syncAutoRotateToggleState();
        updateBoardOrientation(false);
        shogiSocket.emit('get_ai_info', { game_id: currentShogiGameId });
    });

    shogiSocket.on('opponent_disconnected', (data) => {
        setStatus(data?.message || '相手が切断しました。再接続待機中です。');
    });

    shogiSocket.on('opponent_reconnected', (data) => {
        setStatus(data?.message || '相手が再接続しました。');
    });

    shogiSocket.on('match_ended', (data) => {
        cancelBrowserAITurn();
        shogiRoleChoicePending = false;
        setShogiRoleButtonsDisabled(false);
        shogiMatchResumeAllowed = false;
        currentShogiGameId = null;
        shogiAssignedSeat = null;
        shogiAssignedRole = null;
        shogiState = null;
        showShogiRoleModal(false);
        toggleShogiPanels(false);
        clearUiForPendingState('対局が終了しました。新しくマッチングしてください。');
        syncAutoRotateToggleState();
        setShogiMatchStatus(data?.message || '対局を終了しました', true);
    });

    shogiSocket.on('match_error', (data) => {
        shogiRoleChoicePending = false;
        setShogiRoleButtonsDisabled(false);
        shogiMatchmakingInProgress = false;
        setShogiMatchButtons(false);
        setShogiMatchStatus(data?.message || 'マッチングエラーが発生しました', true);
        if (shogiIsCreator && currentShogiGameId && shogiGameMode === 'multiplayer') {
            showShogiRoleModal(true);
        }
    });

    shogiSocket.on('ai_thinking', (data) => {
        if (data && data.game_id && data.game_id !== currentShogiGameId) {
            return;
        }

        setThinkingIndicator(!!(data && data.active), data ? data.player : null, data ? data.algorithm : null);
    });

    shogiSocket.on('game_state', (state) => {
        if (!currentShogiGameId) {
            return;
        }
        if (state.game_type !== 'shogi') {
            return;
        }

        if (state.game_over) {
            setThinkingIndicator(false);
        }

        shogiState = state;
        renderState();
        triggerBrowserAITurnIfNeeded();
    });

    shogiSocket.on('error', (data) => {
        setStatus(`エラー: ${data.message}`);
    });

    shogiSocket.on('ai_info', (info) => {
        shogiAIInfo = info || { black_ai: null, white_ai: null, engine_scope: 'server' };
        syncAIControlsFromInfo();
        triggerBrowserAITurnIfNeeded();
    });

    shogiSocket.on('ai_updated', () => {
        if (currentShogiGameId) {
            shogiSocket.emit('get_ai_info', { game_id: currentShogiGameId });
        }
    });
}

function aiConfigByDifficulty(difficulty) {
    if (difficulty === 'easy') {
        return { depth: 1, iterations: 80, timeBudgetMs: 220 };
    }
    if (difficulty === 'hard') {
        return { depth: 3, iterations: 520, timeBudgetMs: 1800 };
    }
    return { depth: 2, iterations: 220, timeBudgetMs: 800 };
}

function syncAIControlsFromInfo() {
    const black = shogiAIInfo.black_ai;
    const white = shogiAIInfo.white_ai;

    const blackEnabled = !!black;
    const whiteEnabled = !!white;

    document.getElementById('black-ai-enable').checked = blackEnabled;
    document.getElementById('white-ai-enable').checked = whiteEnabled;

    document.getElementById('black-ai-engine').value = blackEnabled ? normalizeShogiEngine(black.engine || black.algorithm || 'rule_based') : 'rule_based';
    document.getElementById('white-ai-engine').value = whiteEnabled ? normalizeShogiEngine(white.engine || white.algorithm || 'rule_based') : 'rule_based';

    document.getElementById('black-ai-difficulty').value = blackEnabled ? (black.difficulty || 'medium') : 'medium';
    document.getElementById('white-ai-difficulty').value = whiteEnabled ? (white.difficulty || 'medium') : 'medium';
}

function emitAISetting(color) {
    if (shogiGameMode === 'multiplayer') {
        return;
    }
    if (!currentShogiGameId) {
        return;
    }
    const isBlack = color === 'black';
    const enabled = document.getElementById(isBlack ? 'black-ai-enable' : 'white-ai-enable').checked;
    const engine = document.getElementById(isBlack ? 'black-ai-engine' : 'white-ai-engine').value;
    const difficulty = document.getElementById(isBlack ? 'black-ai-difficulty' : 'white-ai-difficulty').value;
    const engineScope = resolveSingleplayerEngineScopeFromControls();

    if (!enabled || engine === 'none') {
        shogiSocket.emit('set_ai', {
            game_id: currentShogiGameId,
            color,
            algorithm: 'none',
            engine: 'none',
            difficulty,
            engine_scope: engineScope
        });
        return;
    }

    const config = aiConfigByDifficulty(difficulty);
    shogiSocket.emit('set_ai', {
        game_id: currentShogiGameId,
        color,
        algorithm: engine,
        engine,
        difficulty,
        depth: config.depth,
        iterations: config.iterations,
        time_budget_ms: config.timeBudgetMs,
        engine_scope: engineScope
    });
}

function getMovesFromCell(row, col) {
    if (!shogiState) return [];
    return shogiState.valid_moves.filter((move) => {
        return move.from && move.from[0] === row && move.from[1] === col;
    });
}

function getDropMoves(pieceLabel) {
    if (!shogiState) return [];
    return shogiState.valid_moves.filter((move) => move.drop_piece === pieceLabel);
}

function isMyShogiTurn() {
    if (!shogiState || !shogiAssignedSeat) return false;
    if (shogiAssignedSeat === 'first') return shogiState.current_player === 1;
    if (shogiAssignedSeat === 'second') return shogiState.current_player === 2;
    return false;
}

function ownsPiece(piece) {
    if (!shogiState || piece === 0) return false;
    if (shogiState.current_player === 1) return piece > 0;
    return piece < 0;
}

function onBoardCellClick(event) {
    if (!shogiState || shogiState.game_over) return;
    if (!isMyShogiTurn()) {
        setStatus('現在あなたのターンではありません');
        return;
    }

    const row = parseInt(event.currentTarget.dataset.row, 10);
    const col = parseInt(event.currentTarget.dataset.col, 10);
    const boardPiece = shogiState.board[row][col];

    if (selectedDropPiece) {
        const validDrop = getDropMoves(selectedDropPiece).find((move) => move.to[0] === row && move.to[1] === col);
        if (!validDrop) {
            setStatus('その位置には打てません');
            return;
        }

        shogiSocket.emit('make_move', {
            game_id: currentShogiGameId,
            move: {
                drop_piece: selectedDropPiece,
                to: [row, col],
                promote: false
            }
        });
        selectedDropPiece = null;
        selectedFrom = null;
        return;
    }

    if (selectedFrom) {
        const candidates = getMovesFromCell(selectedFrom.row, selectedFrom.col).filter((move) => {
            return move.to[0] === row && move.to[1] === col;
        });

        if (candidates.length === 0) {
            if (ownsPiece(boardPiece)) {
                selectedFrom = { row, col };
                renderState();
                return;
            }
            selectedFrom = null;
            renderState();
            return;
        }

        let selectedMove = candidates[0];
        if (candidates.length === 2) {
            const shouldPromote = window.confirm('成りますか？\nOK: 成る / キャンセル: 成らない');
            selectedMove = candidates.find((move) => move.promote === shouldPromote) || candidates[0];
        }

        shogiSocket.emit('make_move', {
            game_id: currentShogiGameId,
            move: {
                from: selectedMove.from,
                to: selectedMove.to,
                promote: selectedMove.promote
            }
        });

        selectedFrom = null;
        selectedDropPiece = null;
        return;
    }

    if (ownsPiece(boardPiece)) {
        selectedFrom = { row, col };
        selectedDropPiece = null;
        renderState();
    }
}

function onHandPieceClick(pieceLabel) {
    if (!shogiState || shogiState.game_over) return;
    if (!isMyShogiTurn()) {
        setStatus('現在あなたのターンではありません');
        return;
    }
    selectedFrom = null;
    selectedDropPiece = selectedDropPiece === pieceLabel ? null : pieceLabel;
    renderState();
}

function renderHands() {
    const blackHands = document.getElementById('black-hands');
    const whiteHands = document.getElementById('white-hands');
    const blackTurn = shogiState.current_player === 1;
    const myTurn = isMyShogiTurn();

    blackHands.innerHTML = '';
    whiteHands.innerHTML = '';

    HAND_ORDER.forEach((pieceLabel) => {
        const blackCount = shogiState.hands.black[pieceLabel] || 0;
        const whiteCount = shogiState.hands.white[pieceLabel] || 0;

        const blackBtn = document.createElement('button');
        blackBtn.type = 'button';
        blackBtn.className = 'hand-piece';
        blackBtn.textContent = `${HAND_JP[pieceLabel]} x${blackCount}`;
        blackBtn.disabled = !(myTurn && blackTurn && blackCount > 0);
        if (selectedDropPiece === pieceLabel && blackTurn) blackBtn.classList.add('selected');
        blackBtn.addEventListener('click', () => onHandPieceClick(pieceLabel));
        blackHands.appendChild(blackBtn);

        const whiteBtn = document.createElement('button');
        whiteBtn.type = 'button';
        whiteBtn.className = 'hand-piece';
        whiteBtn.textContent = `${HAND_JP[pieceLabel]} x${whiteCount}`;
        whiteBtn.disabled = !(myTurn && !blackTurn && whiteCount > 0);
        if (selectedDropPiece === pieceLabel && !blackTurn) whiteBtn.classList.add('selected');
        whiteBtn.addEventListener('click', () => onHandPieceClick(pieceLabel));
        whiteHands.appendChild(whiteBtn);
    });
}

function renderBoard() {
    const cells = document.querySelectorAll('.shogi-cell');

    let moveTargets = [];
    if (selectedFrom) {
        moveTargets = getMovesFromCell(selectedFrom.row, selectedFrom.col);
    } else if (selectedDropPiece) {
        moveTargets = getDropMoves(selectedDropPiece);
    }

    cells.forEach((cell) => {
        const row = parseInt(cell.dataset.row, 10);
        const col = parseInt(cell.dataset.col, 10);
        const piece = shogiState.board[row][col];

        cell.className = 'shogi-cell';
        cell.textContent = '';

        if (selectedFrom && selectedFrom.row === row && selectedFrom.col === col) {
            cell.classList.add('selected-from');
        }

        if (moveTargets.some((move) => move.to[0] === row && move.to[1] === col)) {
            cell.classList.add('valid-target');
        }

        if (shogiState.last_move && shogiState.last_move.to[0] === row && shogiState.last_move.to[1] === col) {
            cell.classList.add('last-move');
        }

        if (piece !== 0) {
            const pieceEl = document.createElement('span');
            pieceEl.className = 'piece';
            if (piece < 0) pieceEl.classList.add('white');
            pieceEl.textContent = PIECE_TEXT[Math.abs(piece)] || '?';
            cell.appendChild(pieceEl);
        }
    });
}

function renderState() {
    if (!shogiState) return;

    const turnChanged = previousTurnPlayer !== null && previousTurnPlayer !== shogiState.current_player;
    const animateTurnChange = turnChanged && !suppressTurnAnimation;

    renderBoard();
    renderHands();

    updateBoardOrientation(animateTurnChange);
    animateTurnIndicator(animateTurnChange);

    const turnEl = document.getElementById('turn-text');
    turnEl.textContent = shogiState.current_player === 1 ? '先手のターン' : '後手のターン';

    previousTurnPlayer = shogiState.current_player;
    suppressTurnAnimation = false;

    if (shogiState.game_over) {
        setThinkingIndicator(false);
        if (shogiState.winner === 1) {
            setStatus(`対局終了: 先手勝ち (${shogiState.result})`);
        } else if (shogiState.winner === 2) {
            setStatus(`対局終了: 後手勝ち (${shogiState.result})`);
        } else {
            setStatus(`対局終了: 引き分け (${shogiState.result})`);
        }
        return;
    }

    if (selectedDropPiece) {
        setStatus(`持ち駒「${HAND_JP[selectedDropPiece]}」の打ち先を選択してください`);
    } else if (selectedFrom) {
        setStatus('移動先を選択してください');
    } else if (shogiState.in_check) {
        setStatus('王手です。回避する手を指してください');
    } else {
        setStatus('駒を選択して指し手を決めてください');
    }
}

function setupControls() {
    document.getElementById('shogi-choose-single-mode-btn').addEventListener('click', () => {
        setShogiGameMode('singleplayer');
    });

    document.getElementById('shogi-choose-multi-mode-btn').addEventListener('click', () => {
        setShogiGameMode('multiplayer');
    });

    document.getElementById('shogi-start-single-btn').addEventListener('click', () => {
        requestShogiSingleStart();
    });

    document.getElementById('shogi-back-from-single-btn').addEventListener('click', () => {
        setShogiGameMode(null);
    });

    document.getElementById('shogi-single-first-btn').addEventListener('click', () => {
        selectShogiSingleSeat('first');
    });

    document.getElementById('shogi-single-second-btn').addEventListener('click', () => {
        selectShogiSingleSeat('second');
    });

    document.getElementById('new-game-btn').addEventListener('click', () => {
        if (!currentShogiGameId) {
            setStatus('先にマッチングを完了してください');
            return;
        }
        clearUiForPendingState('新しい対局を作成しています...');
        shogiSocket.emit('create_game', { game_id: currentShogiGameId, game_type: 'shogi' });
        shogiSocket.emit('get_ai_info', { game_id: currentShogiGameId });
    });

    document.getElementById('reset-btn').addEventListener('click', () => {
        if (!currentShogiGameId) {
            setStatus('先にマッチングを完了してください');
            return;
        }
        clearUiForPendingState('対局をリセットしています...');
        shogiSocket.emit('reset_game', { game_id: currentShogiGameId, game_type: 'shogi' });
        shogiSocket.emit('get_ai_info', { game_id: currentShogiGameId });
    });

    document.getElementById('apply-ai-btn').addEventListener('click', () => {
        if (shogiGameMode === 'multiplayer') {
            setStatus('マルチプレイではAI設定は利用できません');
            return;
        }
        emitAISetting('black');
        emitAISetting('white');
        setStatus('AI設定を反映中です...');
    });

    document.getElementById('clear-ai-btn').addEventListener('click', () => {
        if (shogiGameMode === 'multiplayer') {
            setStatus('マルチプレイではAI設定は利用できません');
            return;
        }
        document.getElementById('black-ai-enable').checked = false;
        document.getElementById('white-ai-enable').checked = false;
        emitAISetting('black');
        emitAISetting('white');
        setStatus('AI設定を無効化しました');
    });

    const autoRotateToggle = document.getElementById('auto-rotate-toggle');
    if (autoRotateToggle) {
        autoRotateToggle.addEventListener('change', (event) => {
            autoRotateBoard = event.currentTarget.checked;
            persistAutoRotatePreference();
            syncAutoRotateToggleState();
            renderState();
        });
    }

    document.getElementById('shogi-start-match-btn').addEventListener('click', () => {
        requestShogiMatchStart();
    });

    document.getElementById('shogi-cancel-match-btn').addEventListener('click', () => {
        requestShogiMatchCancel();
    });

    document.getElementById('shogi-choose-first-btn').addEventListener('click', () => {
        chooseShogiRole('first');
    });

    document.getElementById('shogi-choose-second-btn').addEventListener('click', () => {
        chooseShogiRole('second');
    });
}

document.addEventListener('DOMContentLoaded', () => {
    resetShogiEntryMode();
    selectShogiSingleSeat('first');
    initBoard();
    loadAutoRotatePreference();
    syncAutoRotateToggleState();
    setupSocket();
    setupControls();
    setupWindowResizeSync();
});

window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    if (currentShogiGameId) return;
    resetShogiEntryMode();
});
